"""
steg_6_generalize.py — Steg 6: Kartgeneralisering av reklassificerat NMD-raster.

Steget tar emot tiles från steg 5 (steg_5_filter_islands) och applicerar en serie
generaliseringsoperationer för att ta bort pixelstörningar, miniatyrytor och
oregelbundna klassgränser — utan att förstöra sammanhängande ytor som råkar ligga
på en tilegräns.

HALO-teknik
-----------
Eftersom rastret är uppdelat i tiles bearbetas varje tile normalt oberoende av sina
grannar. Det innebär att en yta som korsar en tilegräns syns som två separata
halvpatchar — och riskerar att elimineras av sieve-filtret trots att den totalt sett
är tillräckligt stor. Halo-tekniken löser detta genom att varje tile läses in med
HALO extra pixlar på alla fyra kanterna (lånade från granntilesarna via en gemensam
VRT-mosaiknivå). Generaliseringen körs på den utökade ytan; därefter klipps enbart
det ursprungliga tile-området ut och skrivs till disk. Halo-pixlarna kastas.

Generaliseringsmetoder (styrs av GENERALIZATION_METHODS i config.py)
--------------------------------------------------------------------
  conn4         : gdal_sieve med 4-grannskap. Eliminerar ytor under
                  successivt ökande MMU-gränser (MMU_STEPS).
  modal         : Majoritetsfilter med kvadratisk kernel. Jämnar ut klassgränser
                  utan att eliminera hela patches.
  semantic      : Semantiskt styrd region-merging. Slår ihop små patches med den
                  angränsande patch som är tematiskt närmast (samma NMD-grupp
                  prioriteras framför stor area).

Efter vald sieve/majority/semantic-metod körs ett valfritt morfologiskt utjämningssteg
(MORPH_SMOOTH_METHOD) som rundar ut pixeltrappor längs klassgränser. Körs här för att 
snabba upp simplifieringen.

Skyddade klasser (GENERALIZE_PROTECTED, t.ex. byggnader och vatten) maskeras
inför varje operation och återställs efteråt — de påverkas inte av generaliseringen.

Kör   : python3 src/steg_6_generalize.py
Kräver: rasterio, numpy, scipy (i venv) · gdal_sieve.py + gdalbuildvrt (system GDAL)
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from config import OUT_BASE, SRC, QML_RECLASSIFY, GENERALIZE_PROTECTED as PROTECTED, COMPRESS, HALO, MMU_STEPS, MMU_CLASS_MAX, MMU_POWERLINE_PATH, MMU_POWERLINE_MAX, GENERALIZATION_METHODS, BUILD_OVERVIEWS, OVERVIEW_LEVELS
from rasterio.enums import Resampling as _Resampling

# ══════════════════════════════════════════════════════════════════════════════
# Logging – två loggers + console
# ══════════════════════════════════════════════════════════════════════════════

_LOGGERS = {}

def _setup_logging(out_base: Path):
    """Skapar två loggfiler:
      debug   - alla level (DEBUG+)  → log/debug_steg_N_namn_ts.log
      summary - INFO+                → summary/summary_steg_N_namn_ts.log + console
    """
    import os
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Läs steg-info från miljövariabler
    step_num = os.getenv("STEP_NUMBER")
    step_name = os.getenv("STEP_NAME")
    
    # Skapa loggfilnamn med eventuell steg-referens
    if step_num and step_name:
        step_suffix = f"steg_{step_num}_{step_name}_{ts}"
    else:
        step_suffix = f"{ts}"
    
    debug_log   = log_dir / f"debug_{step_suffix}.log"
    summary_log = summary_dir / f"summary_{step_suffix}.log"

    fmt_detail  = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # ── Debug-logg (DEBUG+) ──
    dbg = logging.getLogger("pipeline.debug")
    dbg.setLevel(logging.DEBUG)
    dbg_handler = logging.FileHandler(debug_log)
    dbg_handler.setLevel(logging.DEBUG)
    dbg_handler.setFormatter(fmt_detail)
    dbg.addHandler(dbg_handler)

    # ── Summary-logg (INFO+) – både fil och console ──
    summary = logging.getLogger("pipeline.summary")
    summary.setLevel(logging.INFO)

    # Fil-handler
    summary_file_handler = logging.FileHandler(summary_log)
    summary_file_handler.setLevel(logging.INFO)
    summary_file_handler.setFormatter(fmt_summary)
    summary.addHandler(summary_file_handler)

    # Console-handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt_summary)
    summary.addHandler(console_handler)

    _LOGGERS["debug"] = dbg
    _LOGGERS["summary"] = summary
    
    summary.info(f"Pipeline startat")
    summary.info(f"Debug-logg: {debug_log}")
    summary.info(f"Summary-logg: {summary_log}")

# Placeholders – ersätts i __main__ efter OUT_BASE skapats
log  = logging.getLogger("pipeline.debug")
info = logging.getLogger("pipeline.summary")

# ══════════════════════════════════════════════════════════════════════════════
# HALO-parameters
# ══════════════════════════════════════════════════════════════════════════════
# Dessa värden importeras från config.py och bör inte omdefinieras här

def get_nodata_tmp(dtype):
    """Returnera lämpligt temporärt NoData-värde baserat på datatyp.
    
    För uint8: 254 (kolliderar inte med giltiga NMD-klasser 0-254 då 255 är max)
    För uint16: 65535 (max värde, kolliderar inte med NMD-koder 0-999)
    """
    if dtype == np.uint8:
        return np.uint8(254)
    else:
        return np.uint16(65535)

# 4-grannskapsstruktur (Von Neumann-grannskap) för connected-component labeling.
# Används av semantisk generalisering för att identifiera sammanhängande patches.
# Diagonala grannar räknas INTE, vilket ger samma kantdefinition som GDAL:s conn4-sieve.
STRUCT_4 = np.array([[0, 1, 0],
                     [1, 1, 1],
                     [0, 1, 0]], dtype=bool)

# ══════════════════════════════════════════════════════════════════════════════
# Hjälpfunktioner
# ══════════════════════════════════════════════════════════════════════════════

def copy_qml(tif_path: Path):
    if QML_RECLASSIFY.exists():
        shutil.copy2(QML_RECLASSIFY, tif_path.with_suffix(".qml"))
        log.debug("QML kopierad → %s", tif_path.with_suffix(".qml").name)


def build_vrt(paths: list[Path], vrt_path: Path):
    """Bygger en GDAL VRT av angiven lista tif-filer.

    En VRT är ett XML-baserat virtuellt raster som pekar på de underliggande
    tif-filerna utan att kopiera datan. Används som ett gemensamt mosaik-lager
    när halo-läsning ska spänna över tilekanter.
    """
    log.debug("Bygger VRT %s av %d filer", vrt_path.name, len(paths))
    subprocess.run(
        ["gdalbuildvrt", str(vrt_path), *[str(p) for p in paths]],
        capture_output=True, check=True
    )
    log.debug("VRT klar: %s", vrt_path.name)


def build_powerline_mask_vrt(tile_paths: list[Path], out_dir: Path) -> Path | None:
    """Rastrerar kraftlednings-GPKG till ett binärt mask-raster (ett TIF per tile + VRT).

    Returnerar sökväg till VRT om MMU_POWERLINE_PATH är konfigurerat,
    annars None (inaktiverat).

    Masken har värde 1 under kraftledningsgator och 0 övriga pixlar.
    Sparas i out_dir/powerline_mask/ och återanvänds om den redan finns.
    """
    if not MMU_POWERLINE_PATH or not Path(MMU_POWERLINE_PATH).exists():
        return None
    if MMU_POWERLINE_MAX is None:
        return None

    mask_dir = out_dir / "powerline_mask"
    vrt_path = mask_dir / "powerline_mask.vrt"
    if vrt_path.exists():
        log.debug("Kraftlednings-mask VRT finns redan: %s", vrt_path)
        return vrt_path

    mask_dir.mkdir(parents=True, exist_ok=True)
    log.info("Rastrerar kraftledningsgator → %s", mask_dir)

    mask_paths = []
    for i, tile in enumerate(tile_paths, 1):
        if i % 50 == 0 or i == 1:
            log.info("  powerline_mask: %d/%d tiles rastrerad", i, len(tile_paths))
        
        out_mask = mask_dir / tile.name
        if not out_mask.exists():
            with rasterio.open(tile) as src:
                meta = src.meta.copy()
                transform = src.transform
                width = src.width
                height = src.height
                crs = src.crs

            meta.update(dtype="uint8", count=1, nodata=0, compress=COMPRESS)
            result = np.zeros((height, width), dtype="uint8")

            # Rastera GPKG-polygoner till tile-grid med gdal_rasterize
            with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
                tmp_path = Path(f.name)
            try:
                subprocess.run([
                    "gdal_rasterize",
                    "-burn", "1",
                    "-te", str(transform.c), str(transform.f + transform.e * height),
                    str(transform.c + transform.a * width), str(transform.f),
                    "-ts", str(width), str(height),
                    "-ot", "Byte",
                    "-of", "GTiff",
                    str(MMU_POWERLINE_PATH), str(tmp_path),
                ], capture_output=True, check=True)
                with rasterio.open(tmp_path) as msrc:
                    result = msrc.read(1)
            except subprocess.CalledProcessError as e:
                log.warning("gdal_rasterize misslyckades för %s: %s", tile.name, e.stderr.decode()[:200])
            finally:
                tmp_path.unlink(missing_ok=True)

            with rasterio.open(out_mask, "w", **meta) as dst:
                dst.write(result, 1)

        mask_paths.append(out_mask)

    log.info("  powerline_mask: %d/%d tiles rastrerad — bygger VRT", len(mask_paths), len(tile_paths))
    build_vrt(mask_paths, vrt_path)
    log.info("Kraftlednings-mask VRT klar: %d tiles", len(mask_paths))
    return vrt_path


def read_with_halo(vrt_path: Path, tile_path: Path):
    """
    Läser tile + HALO px kant från VRT.

    Returnerar:
      padded_data  - numpy array (h+2*halo, w+2*halo) klippt mot VRT-gränser
      tile_meta    - meta dict för originaltilen (för skrivning av utdata)
      inner_slice  - (row_slice, col_slice) som plockar ut tile-kärnan
    """
    with rasterio.open(vrt_path) as vrt, rasterio.open(tile_path) as tile:
        vt = vrt.transform
        tt = tile.transform
        px = vt.a    # pixelbredd (positiv, meter per pixel i x-led)
        py = vt.e    # pixelhöjd  (negativ, meter per pixel i y-led)

        # Beräkna tilens övre vänstra hörn i pixelkoordinater relativt VRT-origo.
        # round() hanterar floating point-avrundning från georeferensen.
        tile_col = round((tt.c - vt.c) / px)
        tile_row = round((tt.f - vt.f) / py)
        tile_w   = tile.width
        tile_h   = tile.height
        tile_meta = tile.meta.copy()

        # Expandera läsfönstret med HALO px åt varje håll.
        # max/min-klippning säkerställer att vi inte läser utanför VRT-gränserna
        # (kanttilar har ingen granne att låna ifrån).
        x0 = max(0, tile_col - HALO)
        y0 = max(0, tile_row - HALO)
        x1 = min(vrt.width,  tile_col + tile_w + HALO)
        y1 = min(vrt.height, tile_row + tile_h + HALO)

        win  = Window(x0, y0, x1 - x0, y1 - y0)
        data = vrt.read(1, window=win)   # numpy array inkl. halo-kant

    # inner_slice pekar ut tile-kärnan inuti det utvidgade fönstret.
    # Används efter generalisering för att kapa bort halo-pixlarna
    # och skriva tillbaka exakt tilens ursprungliga storlek.
    inner_row = tile_row - y0
    inner_col = tile_col - x0
    inner_slice = (
        slice(inner_row, inner_row + tile_h),
        slice(inner_col, inner_col + tile_w),
    )
    return data, tile_meta, inner_slice


def _apply_sieve(masked: np.ndarray, mmu: int, conn: int, meta_tmp: dict) -> np.ndarray:
    """Kör gdal_sieve.py på ett förberett (maskerat) numpy-array.

    Anroparen ansvarar för att sätta skyddade pixlar till NODATA_TMP i `masked`
    och för att återinsätta originalvärdena i returresultatet.
    Returnerar råresultatet direkt från sieve — ingen NoData-justering.
    """
    with tempfile.NamedTemporaryFile(suffix="_in.tif", delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix="_out.tif", delete=False) as f2:
        in_p = Path(f1.name)
        out_p = Path(f2.name)
    try:
        with rasterio.open(in_p, "w", **meta_tmp) as dst:
            dst.write(masked, 1)
        flag = "-4" if conn == 4 else "-8"
        subprocess.run(
            ["gdal_sieve.py", "-st", str(mmu), flag, str(in_p), str(out_p)],
            capture_output=True, check=True,
        )
        with rasterio.open(out_p) as src:
            return src.read(1)
    finally:
        in_p.unlink(missing_ok=True)
        out_p.unlink(missing_ok=True)


def run_sieve(data: np.ndarray, mmu: int, conn: int,
              extra_protected: frozenset = frozenset(),
              powerline_mask: np.ndarray | None = None,
              run_powerline_sieve: bool = False) -> np.ndarray:
    """Kör gdal_sieve på en numpy-array och returnerar det silade resultatet.

    Sieve-filtret eliminerar sammanhängande pixelgrupper (patches) som är
    mindre än mmu pixlar. Varje sådan patch ersätts med värdet hos den
    störst angränsande patchen — dvs. en ytbaserad region-merging.

    Skyddade klasser (PROTECTED + extra_protected) maskeras till NODATA_TMP inför sieve
    så att de aldrig berörs, och återställs sedan från originaldatan.

    extra_protected — klasser från MMU_CLASS_MAX vars max_mmu understiger aktuellt mmu-steg;
                       dessa läggs till som tilfälligt skyddade för detta steg.

    powerline_mask — om angiven, körs kraftledningspixlar ALLTID separat från övrig
                     mark (de exkluderas från huvud-sieve oavsett MMU-steg).

    run_powerline_sieve — om True körs ett andra sieve-pass enbart på kraftlednings-
                          pixlar (med all annan mark maskad som NoData). Sätts True
                          när mmu <= MMU_POWERLINE_MAX. Därigenom kan kraftlednings-
                          pixlar bara absorberas av grannar som OCKSÅ ligger under
                          kraftledningen, inte av den omgivande skogen.

    Flöde (med aktiv kraftlednings-mask):
      1. Huvud-sieve: kraftledning + skyddade klasser → NoData; sieve för övrig mark
      2. Om run_powerline_sieve: kraftlednings-sieve: allt utom kraftledning → NoData
      3. Merge: kraftledningsresultat ersätter huvud-resultatet där masken är aktiv
    """
    log.debug("run_sieve: mmu=%d conn=%d  data=%s  extra_prot=%s  powerline=%s  pl_sieve=%s",
              mmu, conn, data.shape, extra_protected,
              powerline_mask is not None and powerline_mask.any(), run_powerline_sieve)
    
    # Hämta lämpligt NODATA_TMP baserat på datatyp
    NODATA_TMP = get_nodata_tmp(data.dtype)
    
    # Bygg en minimal meta för temp-filen (transform spelar ingen roll för sieve;
    # gdal_sieve arbetar enbart med pixelvärden och grannskap, inte geografi)
    from rasterio.transform import from_bounds
    dummy_transform = from_bounds(0, 0, data.shape[1], data.shape[0],
                                  data.shape[1], data.shape[0])
    meta_tmp = {
        "driver": "GTiff", "dtype": data.dtype, "count": 1,
        "height": data.shape[0], "width": data.shape[1],
        "crs": "EPSG:3006", "transform": dummy_transform,
        "compress": None, "nodata": int(NODATA_TMP),
    }
    # Kombinera permanenta och stegspecifika skyddade klasser
    all_protected = list(PROTECTED | extra_protected)
    prot_mask = np.isin(data, all_protected)

    # --- Huvud-sieve: mark utanför kraftledningen ---
    # Kraftledningspixlar exkluderas alltid från huvud-sieve (oavsett MMU-steg)
    # så att de inte absorberas av den omgivande landklassen.
    main_prot = prot_mask.copy()
    if powerline_mask is not None and powerline_mask.shape == data.shape:
        main_prot = main_prot | powerline_mask

    masked = data.copy()
    masked[main_prot] = NODATA_TMP   # Dölj skyddade klasser + kraftledning som NoData
    sieved = _apply_sieve(masked, mmu, conn, meta_tmp)
    sieved[main_prot] = data[main_prot]   # Återinsätt kraftledning + vatten etc.

    # --- Separat sieve för kraftledningsmark (mmu <= MMU_POWERLINE_MAX) ---
    # Kraftledningspixlar sievas enbart mot varandra: all annan mark maskeras
    # som NoData, vilket förhindrar absorption av angränsande skogsklasser.
    if run_powerline_sieve and powerline_mask is not None and powerline_mask.shape == data.shape:
        # Skyddade klasser + pixlar utanför kraftledningen → NoData
        pl_prot = prot_mask | ~powerline_mask
        pl_masked = data.copy()
        pl_masked[pl_prot] = NODATA_TMP
        pl_sieved = _apply_sieve(pl_masked, mmu, conn, meta_tmp)
        pl_sieved[pl_prot] = data[pl_prot]   # Återinsätt allt som inte är aktiv kraftledning
        # Merge: kraftledningsresultatet gäller där masken är aktiv och pixeln ej
        # är permanent skyddad (vatten/bebyggelse bör aldrig ändras).
        pl_domain = powerline_mask & ~prot_mask
        sieved = np.where(pl_domain, pl_sieved, sieved)

    changed = int(np.sum(sieved != data))
    log.debug("run_sieve klar: %d px ändrade (%.1f%%)",
              changed, changed / data.size * 100)
    return sieved


def _build_overviews(path: Path) -> None:
    """Bygger pyramidnivåer för en TIF-fil om BUILD_OVERVIEWS är aktiverat."""
    if BUILD_OVERVIEWS and OVERVIEW_LEVELS:
        try:
            with rasterio.open(path, "r+") as ds:
                ds.build_overviews(OVERVIEW_LEVELS, _Resampling.nearest)
                ds.update_tags(ns="rio_overview", resampling="nearest")
        except Exception as _ov_exc:
            log.warning("_build_overviews: misslyckades för %s (%s) — overviews hoppas över",
                        path.name, _ov_exc)


# ══════════════════════════════════════════════════════════════════════════════
# Steg 4: Generalisering med halo – steg-för-steg över alla tiles
# ══════════════════════════════════════════════════════════════════════════════

# Antal parallella processer — lämna 2 kärnor fria för OS/IO
N_WORKERS = max(1, (os.cpu_count() or 1) - 2)


def _sieve_tile_worker(args):
    """Worker för ProcessPoolExecutor: kör ett sieve-pass på en tile.

    Flöde:
      1. Stöd för återupptagen körning — hoppa över om utfilen redan finns.
      2. Läs tile + halo från VRT-mosaiken.
      3. Kör sieve på det utvidgade fönstret.
      4. Klipp bort halo med inner_slice och skriv tile-utdata.
    """
    prev_vrt, tile, out_path = Path(args[0]), Path(args[1]), Path(args[2])
    mmu, conn = args[3], args[4]
    extra_protected: frozenset = args[5]
    powerline_vrt = Path(args[6]) if len(args) > 6 and args[6] else None

    # Återupptagen körning: utfil finns redan → returnera direkt utan bearbetning
    if out_path.exists():
        with rasterio.open(tile) as _src:
            orig = _src.read(1)
        return str(out_path), 0, orig.shape
    # Läs tile med halo-kant från det gemensamma VRT-mosaiken
    padded, tile_meta, inner = read_with_halo(prev_vrt, tile)
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(tile) as _src:
        orig = _src.read(1)

    # Läs kraftlednings-mask om konfigurerat — alltid, oavsett MMU-steg.
    # Vid mmu <= MMU_POWERLINE_MAX körs ett separat sieve-pass för kraftledningsmark.
    # Vid mmu > MMU_POWERLINE_MAX är kraftledningspixlar fortfarande exkluderade från
    # huvud-sieve (ingen separat pass) → de förblir oförändrade ("frysta").
    pl_mask = None
    if powerline_vrt is not None and MMU_POWERLINE_MAX is not None:
        pl_padded, _, pl_inner = read_with_halo(powerline_vrt, tile)
        pl_mask = pl_padded.astype(bool)

    run_pl_sieve = (pl_mask is not None and MMU_POWERLINE_MAX is not None
                    and mmu <= MMU_POWERLINE_MAX)

    # Kör sieve på hela det utvidgade fönstret; [inner] klipper bort halon innan skrivning
    result  = run_sieve(padded, mmu, conn, extra_protected, pl_mask, run_pl_sieve)[inner]
    changed = int(np.sum(result != orig))
    tile_meta.update(compress=COMPRESS)
    with rasterio.open(out_path, "w", **tile_meta) as dst:
        dst.write(result, 1)
    copy_qml(out_path)
    _build_overviews(out_path)
    return str(out_path), changed, orig.shape


def sieve_halo(tile_paths: list[Path], filled_paths: list[Path], conn: int):
    """Kör sieve-filtrering med halo-överlapp över alla tiles i flera MMU-steg.

    Varje MMU-steg läser från ett gemensamt VRT-mosaik (prev_vrt) som uppdateras
    efter varje steg — dvs. steg N+1 ser resultatet från steg N. Detta ger en
    kumulativ effekt: successivt allt större ytor elimineras.

    Mellanresultat (lägre MMU-steg) raderas efter körningen; endast det slutliga
    högsta MMU-steget sparas på disk.
    """
    label    = f"conn{conn}"
    out_dir = OUT_BASE / "steg_6_generalize" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    t0_step  = time.time()

    # Bygg ett initialt VRT-mosaik av indata (steg 5-output) om det inte redan finns
    src_dir  = filled_paths[0].parent.name if filled_paths else "input"
    prev_vrt = OUT_BASE / f"{src_dir}_mosaic.vrt"
    if not prev_vrt.exists():
        build_vrt(filled_paths, prev_vrt)

    # Bygg kraftlednings-mask VRT (om konfigurerat) — en gång per variant
    powerline_vrt = build_powerline_mask_vrt(tile_paths, out_dir)
    if powerline_vrt:
        info.info("Kraftlednings-mask aktiv: MMU_POWERLINE_MAX=%d px  (%s)",
                  MMU_POWERLINE_MAX, powerline_vrt.name)

    info.info("Steg 6 Sieve-%s: %d MMU-steg x %d tiles (halo=%dpx)",
              label, len(MMU_STEPS), len(tile_paths), HALO)

    for mmu in MMU_STEPS:
        # Klasser vars max_mmu är ljägre än aktuellt steg skyddas temporärt detta steg.
        extra_protected = frozenset(cls for cls, max_mmu in MMU_CLASS_MAX.items() if mmu > max_mmu)
        step_outputs  = []
        t0            = time.time()
        total_changed = 0
        log.debug("%s mmu=%d: startar  extra_prot=%s", label, mmu, extra_protected)

        # Bygg argument-tupler; argument måste vara primitiva typer för pickle (multiprocessing)
        # powerline_vrt skickas med som str (None → "") — workern ignorerar om tom
        pl_vrt_str = str(powerline_vrt) if powerline_vrt else ""
        task_args = [
            (str(prev_vrt), str(tile),
             str(out_dir / f"{tile.stem}_{label}_mmu{mmu:03d}.tif"),
             mmu, conn, extra_protected, pl_vrt_str)
            for tile in tile_paths
        ]
        with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
            for out_path_str, changed, _ in executor.map(_sieve_tile_worker, task_args):
                step_outputs.append(Path(out_path_str))
                total_changed += changed

        # Uppdatera prev_vrt till detta steps output — nästa MMU-steg läser härifrån
        step_vrt = out_dir / f"_vrt_mmu{mmu:03d}.vrt"
        build_vrt(step_outputs, step_vrt)
        prev_vrt = step_vrt
        elapsed  = time.time() - t0
        extra_str = f"  (skyddar {sorted(extra_protected)})" if extra_protected else ""
        if powerline_vrt and MMU_POWERLINE_MAX is not None:
            if mmu <= MMU_POWERLINE_MAX:
                pl_str = f"  (kraftledning sievas separat, steg {mmu}<={MMU_POWERLINE_MAX})"
            else:
                pl_str = f"  (kraftledning fryst, steg {mmu}>{MMU_POWERLINE_MAX})"
        else:
            pl_str = ""
        info.info("  %-10s mmu=%3dpx  totalt %9d px ändrade  %.1fs%s%s",
                  label, mmu, total_changed, elapsed, extra_str, pl_str)

    # Rensa intermediära TIF-filer (lägre MMU-steg) — behåll bara det slutliga steget.
    # VRT-filerna som pekade på mellanresultaten raderas också.
    last_mmu = max(MMU_STEPS)
    for tif in out_dir.glob("*.tif"):
        if f"_mmu{last_mmu:03d}" not in tif.stem:
            tif.unlink()
            log.debug("  Rensat intermediate: %s", tif.name)
    for vrt in out_dir.glob("_vrt_mmu*.vrt"):
        vrt.unlink()
    log.debug("  Behåller endast mmu%03d", last_mmu)

    _elapsed = time.time() - t0_step
    info.info("Steg 6 Sieve-%s KLAR  %.1f min (%.0fs)", label, _elapsed / 60, _elapsed)


# ══════════════════════════════════════════════════════════════════════════════
# Huvudprogram
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    _setup_logging(OUT_BASE)
    log  = _LOGGERS["debug"]
    info = _LOGGERS["summary"]
    
    # Checkpoint: Hoppa över om steg 6 redan är färdigt
    checkpoint_file = OUT_BASE / ".steg_6_complete"
    if checkpoint_file.exists():
        info.info("════════════════════════════════════════════════════════════")
        info.info("Steg 6: HOPPAR ÖVER (redan färdigt enligt checkpoint)")
        info.info("════════════════════════════════════════════════════════════")
        sys.exit(0)
    
    t_total = time.time()
    ts_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6: Generalisering (halo-teknik)")
    info.info("Källmapp  : %s", SRC)
    info.info("Utmapp    : %s", OUT_BASE)
    info.info("Halo      : %d px", HALO)
    info.info("Skyddade klasser: %s", sorted(PROTECTED))
    info.info("MMU-steg  : %s px", MMU_STEPS)
    info.info("Aktiva generaliseringsmetoder: %s", sorted(GENERALIZATION_METHODS))
    info.info("══════════════════════════════════════════════════════════")

    # Rensa inaktuella metod-mappar (metoder som tagits bort från config)
    import shutil
    all_methods = {"conn4", "conn8"}
    for method in all_methods - GENERALIZATION_METHODS:
        stale_dir = OUT_BASE / "steg_6_generalize" / method
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
            info.info("  Raderat inaktuell metod-mapp: %s", stale_dir.name)

    # Rensa inaktuella MMU-filer inom aktiva sieve-mappar
    active_mmu_labels = {f"_mmu{mmu:03d}" for mmu in MMU_STEPS}
    for conn in ("conn4", "conn8"):
        if conn not in GENERALIZATION_METHODS:
            continue
        sieve_dir = OUT_BASE / "steg_6_generalize" / conn
        if not sieve_dir.exists():
            continue
        for tif in sieve_dir.glob("*.tif"):
            if not any(lbl in tif.stem for lbl in active_mmu_labels):
                tif.unlink()
                info.info("  Raderat inaktuell MMU-fil: %s", tif.name)

    # Steg 6 (Generalisering) läser från steg_4_filter_lakes eller steg_5_filter_islands 
    # Kolla först om steg 5 (fylla öar) kördes
    landscape_dir = OUT_BASE / "steg_5_filter_islands"
    if not landscape_dir.exists():
        landscape_dir = OUT_BASE / "steg_4_filter_lakes"
    if not landscape_dir.exists():
        landscape_dir = OUT_BASE / "steg_3_dissolve"

    if not landscape_dir.exists():
        info.error("Ingen input-katalog hittad. Kör Steg 1-5 först.")
        raise FileNotFoundError(f"Varken steg_4_filter_lakes/ eller steg_5_filter_islands/")

    landscape_paths = sorted(landscape_dir.glob("*.tif"))
    tile_paths = sorted((OUT_BASE / "steg_1_reclassify").glob("*.tif")) if (OUT_BASE / "steg_1_reclassify").exists() else []

    # Kör bara aktiverade generaliseringsmetoder
    if "conn4" in GENERALIZATION_METHODS:
        info.info("\nSteg 6: Sieve conn4 (med halo)")
        sieve_halo(tile_paths, landscape_paths, conn=4)

    if "conn8" in GENERALIZATION_METHODS:
        info.info("\nSteg 6: Sieve conn8 (med halo)")
        sieve_halo(tile_paths, landscape_paths, conn=8)

    elapsed = time.time() - t_total
    info.info("══════════════════════════════════════════════════════════")
    info.info("Steg 6 klart  totaltid: %.1f min (%.0fs)", elapsed / 60, elapsed)
    info.info("Utdata: %s", OUT_BASE)
    info.info("═══════════════════════════════════════════════════════════════")

    # Bygg en _mosaic.vrt per metodkatalog så att resultaten kan öppnas i QGIS direkt
    generalize_dir = OUT_BASE / "steg_6_generalize"
    for method_dir in sorted(generalize_dir.iterdir()) if generalize_dir.exists() else []:
        if not method_dir.is_dir():
            continue
        tifs = sorted(method_dir.glob("*.tif"))
        if not tifs:
            continue
        vrt_path = method_dir / "_mosaic.vrt"
        r = subprocess.run(
            ["gdalbuildvrt", str(vrt_path), *[str(t) for t in tifs]],
            capture_output=True,
        )
        if r.returncode == 0:
            log.info("VRT: %s (%d tiles)", vrt_path, len(tifs))
        else:
            log.warning("Kunde inte bygga VRT för %s", method_dir)
    
    # Skapa checkpoint-fil för att indikera att steg 6 är färdigt
    checkpoint_file = OUT_BASE / ".steg_6_complete"
    checkpoint_file.touch()
    info.info("Checkpoint skapad: %s", checkpoint_file.name)