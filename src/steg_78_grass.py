"""
steg_78_grass.py — Steg 7+8 kombinerat: r.external → r.patch → r.to.vect →
                    v.generalize → v.out.ogr i en enda GRASS-session.

Ersätter steg_7_vectorize.py + steg_8_simplify.py när GRASS används som backend.
Ingen mellanlanding i GPKG — polygoniseringen sker direkt i GRASS-topologin.

Fördelar vs separat steg 7 + steg 8:
  - Inga topologiska sömglapp
  - Slipper skriva/läsa 1.8 GB GPKG i steg 7
  - Enklare kod

Kräver: GRASS 8.x med r.external, r.patch, r.to.vect, v.generalize, v.out.ogr
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from config import (
    OUT_BASE, SRC, TILE_SIZE,
    MORPH_SMOOTH_METHOD, MORPH_SMOOTH_RADIUS, MORPH_ONLY,
    SIMPLIFY_BACKEND,
    GRASS_SIMPLIFY_METHOD,
    GRASS_CHAIKEN_THRESHOLD, GRASS_DOUGLAS_THRESHOLD,
    GRASS_SLIDING_ITERATIONS, GRASS_SLIDING_THRESHOLD, GRASS_SLIDING_SLIDE,
    GRASS_VECTOR_MEMORY, GRASS_OMP_THREADS,
    GRASS_CHUNK_TILE_ROWS, GRASS_CHUNK_OVERLAP,
)


def _setup_logging(out_base):
    import os as _os
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = _os.getenv("STEP_NUMBER")
    step_name = _os.getenv("STEP_NAME")
    if step_num and step_name:
        suffix = f"steg_{step_num}_{step_name}_{ts}"
    else:
        suffix = ts
    fmt_d = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                               datefmt="%Y-%m-%d %H:%M:%S")
    fmt_s = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s",
                               datefmt="%H:%M:%S")
    log = logging.getLogger("pipeline.steg78")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.handlers.clear()
    h_d = logging.FileHandler(log_dir / f"debug_{suffix}.log")
    h_d.setLevel(logging.DEBUG); h_d.setFormatter(fmt_d); log.addHandler(h_d)
    h_s = logging.FileHandler(summary_dir / f"summary_{suffix}.log")
    h_s.setLevel(logging.INFO);  h_s.setFormatter(fmt_s); log.addHandler(h_s)
    h_c = logging.StreamHandler()
    h_c.setLevel(logging.INFO);  h_c.setFormatter(fmt_s); log.addHandler(h_c)
    return log


_GRASS_HEADER = """\
#!/usr/bin/env python3
import subprocess, sys

def run(cmd, desc=""):
    r = subprocess.run(cmd, capture_output=True, text=True)
    # Filtrera bort ofarliga GDAL-varningar för NoData-tiles (utanför Sverige)
    _ignore = "no valid pixels found in sampling"
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.stderr.strip():
        filtered = "\\n".join(l for l in r.stderr.splitlines() if _ignore not in l)
        if filtered.strip():
            print(filtered.strip(), file=sys.stderr)
    if r.returncode != 0:
        print(f"FAILED: {desc or cmd[0]}", file=sys.stderr)
        sys.exit(r.returncode)
    if desc:
        print(f"  OK: {desc}")
"""


def _run_grass_78(
    tif_files: list,
    variant_name: str,
    output_gpkg: Path,
    method: str,
    douglas_threshold: float,
    chaiken_threshold: float,
    log,
    checkpoint_prefix: str = None,
):
    """
    Kör r.external x N → r.patch → r.to.vect → v.generalize → v.out.ogr
    i en enda GRASS --tmp-project-session.

    tif_files      : sorterad lista med Path till steg_6-tile-TIFFar
    variant_name   : t.ex. 'conn4_morph_disk_r02'  (används som rasternamn i GRASS)
    output_gpkg    : sökväg till slutlig GPKG

    Checkpoint: raw_vect sparas som GPKG direkt efter r.to.vect. Om checkpointen
    finns vid nästa körning hoppas r.external+r.patch+r.to.vect över och
    GRASS börjar direkt med v.in.ogr → v.generalize.
    """
    if not tif_files:
        log.error(f"[{variant_name}] inga TIF-filer hittades")
        return False

    # Checkpoint: raw polygon GPKG sparas bredvid output_gpkg.
    # checkpoint_prefix styr filnamnet — i chunked mode ges ett unikt prefix per
    # chunk så att varje session har sin egen checkpoint.
    _cp_prefix = checkpoint_prefix if checkpoint_prefix else variant_name
    raw_vect_gpkg = output_gpkg.with_name(f"{_cp_prefix}_raw_vect.gpkg")
    have_checkpoint = raw_vect_gpkg.exists()

    if have_checkpoint:
        log.info(f"[{variant_name}] Checkpoint finns — hoppar r.external+r.patch+r.to.vect")
    else:
        log.info(f"[{variant_name}] {len(tif_files)} tiles — "
                 f"r.external → r.patch → r.to.vect → checkpoint → v.generalize({method}) → v.out.ogr")

    # ── Bygg GRASS-skript ──────────────────────────────────────────────────
    lines = [_GRASS_HEADER]

    if have_checkpoint:
        # Starta från sparad raw_vect
        lines.append(
            f'run(["v.in.ogr", "input={raw_vect_gpkg}", "output=raw_vect", '
            f'"--overwrite", "--quiet"], "v.in.ogr checkpoint")'
        )
    else:
        # 1) r.external: registrera alla tiles utan att kopiera data
        rmap_names = []
        for i, tif in enumerate(tif_files):
            rname = f"tile_{i:05d}"
            rmap_names.append(rname)
            lines.append(
                f'run(["r.external", "input={tif}", "output={rname}", '
                f'"--overwrite", "--quiet"], "{rname}")'
            )

        # 2) g.region: sätt extent + resolution efter alla tiles
        maps_csv = ",".join(rmap_names)
        lines.append(
            f'run(["g.region", "raster={maps_csv}", "--verbose"], "g.region")'
        )

        # 3) r.patch
        if len(rmap_names) == 1:
            lines.append(
                f'run(["g.rename", "raster={rmap_names[0]},mosaic", '
                f'"--overwrite"], "r.patch (rename single tile)")'
            )
        else:
            lines.append(
                f'run(["r.patch", "input={maps_csv}", "output=mosaic", '
                f'"--overwrite", "--verbose"], "r.patch")'
            )

        # 4) r.to.vect
        lines.append(
            'run(["r.to.vect", "input=mosaic", "output=raw_vect", '
            '"type=area", "column=DN", "--overwrite", "--verbose"], "r.to.vect")'
        )

        # 4b) Spara checkpoint — om v.generalize kraschar kan nästa körning
        #     hoppa direkt hit
        lines.append(
            f'run(["v.out.ogr", "input=raw_vect", "output={raw_vect_gpkg}", '
            f'"output_layer=raw_vect", "format=GPKG", "--overwrite", "--quiet"], '
            f'"checkpoint raw_vect")'
        )


    # 5) v.generalize
    if method == "douglas":
        lines.append(
            f'run(["v.generalize", "input=raw_vect", "output=simplified", '
            f'"method=douglas", "threshold={douglas_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (douglas)")'
        )
    elif method == "chaiken":
        lines.append(
            f'run(["v.generalize", "input=raw_vect", "output=simplified", '
            f'"method=chaiken", "threshold={chaiken_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (chaiken)")'
        )
    elif method == "douglas+chaiken":
        lines.append(
            f'run(["v.generalize", "input=raw_vect", "output=after_dp", '
            f'"method=douglas", "threshold={douglas_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (douglas)")'
        )
        lines.append(
            f'run(["v.generalize", "input=after_dp", "output=simplified", '
            f'"method=chaiken", "threshold={chaiken_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (chaiken)")'
        )
    elif method == "chaiken+douglas":
        lines.append(
            f'run(["v.generalize", "input=raw_vect", "output=after_chaiken", '
            f'"method=chaiken", "threshold={chaiken_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (chaiken)")'
        )
        lines.append(
            f'run(["v.generalize", "input=after_chaiken", "output=simplified", '
            f'"method=douglas", "threshold={douglas_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (douglas)")'
        )
    elif method == "sliding_avg":
        lines.append(
            f'run(["v.generalize", "input=raw_vect", "output=simplified", '
            f'"method=sliding_averaging", "threshold={GRASS_SLIDING_THRESHOLD:.2f}", '
            f'"iterations={GRASS_SLIDING_ITERATIONS}", "slide={GRASS_SLIDING_SLIDE:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (sliding_averaging)")'
        )
    elif method == "douglas+sliding_avg":
        lines.append(
            f'run(["v.generalize", "input=raw_vect", "output=after_dp", '
            f'"method=douglas", "threshold={douglas_threshold:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (douglas)")'
        )
        lines.append(
            f'run(["v.generalize", "input=after_dp", "output=simplified", '
            f'"method=sliding_averaging", "threshold={GRASS_SLIDING_THRESHOLD:.2f}", '
            f'"iterations={GRASS_SLIDING_ITERATIONS}", "slide={GRASS_SLIDING_SLIDE:.2f}", '
            f'"--overwrite", "--verbose"], "v.generalize (sliding_averaging)")'
        )
    else:
        log.error(f"Okänd GRASS_SIMPLIFY_METHOD: '{method}'")
        return False

    # 6) v.clean borttagen: data från r.to.vect är redan topologiskt ren
    # (kommen från raster). v.clean fann inget att korrigera (Snapped vertices: 0,
    # Breaks: 0, Removed duplicates: 0) men kraschade med spatial index-fel
    # vid 25M+ primitiver. v.out.ogr läser direkt från simplified istället.

    # 7) v.out.ogr — output_layer sätter internt lagernamn i GPKG till variantnamnet
    lines.append(
        f'run(["v.out.ogr", "input=simplified", "output={output_gpkg}", '
        f'"output_layer={variant_name}", '
        f'"format=GPKG", "--overwrite", "--verbose"], "v.out.ogr")'
    )

    script_text = "\n".join(lines)

    # ── Välj tmpdir ────────────────────────────────────────────────────────
    tmpbase = None
    shm = Path("/dev/shm")
    if shm.exists():
        try:
            if shutil.disk_usage(str(shm)).free > 8 * 2**30:
                tmpbase = str(shm)
        except OSError:
            pass
    gtmp = Path(tempfile.mkdtemp(prefix=f"grass78_{variant_name}_", dir=tmpbase))

    try:
        script_path = gtmp / "run.py"
        script_path.write_text(script_text)
        genv = {
            **os.environ,
            "GRASS_VECTOR_MEMORY": str(GRASS_VECTOR_MEMORY),
            "OMP_NUM_THREADS":     str(GRASS_OMP_THREADS),
        }
        t0 = time.time()
        proc = subprocess.Popen(
            ["grass", "--tmp-project", "EPSG:3006", "--exec", "python3", str(script_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=genv,
        )
        for ln in proc.stdout:
            ln = ln.strip()
            if ln:
                log.info(f"  [grass] {ln}")
        proc.wait()
    finally:
        shutil.rmtree(gtmp, ignore_errors=True)

    if proc.returncode != 0:
        log.error(f"[{variant_name}] GRASS returnerade kod {proc.returncode}")
        return False

    if not output_gpkg.exists():
        log.error(f"[{variant_name}] v.out.ogr producerade ingen fil")
        return False

    # GEOS-validitet kan skilja sig från GRASS topologikorrektet — kör makevalid
    # som ett säkerhetsnät. Skriver över filen på plats via en tmp-fil.
    valid_tmp = output_gpkg.with_suffix(".valid_tmp.gpkg")
    r_mv = subprocess.run(
        ["ogr2ogr", "-f", "GPKG", "-makevalid", str(valid_tmp), str(output_gpkg)],
        capture_output=True, text=True,
    )
    if r_mv.returncode == 0 and valid_tmp.exists():
        output_gpkg.unlink()
        valid_tmp.rename(output_gpkg)
    else:
        log.warning(f"[{variant_name}] ogr2ogr -makevalid misslyckades — behåller original")
        valid_tmp.unlink(missing_ok=True)

    elapsed = time.time() - t0
    log.info(f"[{variant_name}] ✓ {output_gpkg.name} "
             f"({output_gpkg.stat().st_size/1024**2:.1f} MB, {elapsed/60:.1f} min)")
    return True


if __name__ == "__main__":
    t_start = time.time()
    log = _setup_logging(OUT_BASE)

    # Om steg 6b körts (steg_6b_expand_water/ finns och innehåller kataloger)
    # används den som källa, annars faller vi tillbaka på steg_6_generalize/.
    _gen6b = OUT_BASE / "steg_6b_expand_water"
    if _gen6b.exists() and any(d.is_dir() for d in _gen6b.iterdir()):
        gen6_dir = _gen6b
        log.info("Källa: steg_6b_expand_water/ (expand-water kördes)")
    else:
        gen6_dir = OUT_BASE / "steg_6_generalize"
        log.info("Källa: steg_6_generalize/ (steg 6b saknas)")
    output_dir = OUT_BASE / "steg_8_simplify"   # skriver direkt till steg_8 (steg_7 hoppas över)
    output_dir.mkdir(parents=True, exist_ok=True)

    method = GRASS_SIMPLIFY_METHOD
    if method == "douglas":
        dp  = int(round(GRASS_DOUGLAS_THRESHOLD))
        sfx = f"dp{dp}"
    elif method == "chaiken":
        ch  = int(round(GRASS_CHAIKEN_THRESHOLD))
        sfx = f"chaiken_t{ch}"
    elif method == "sliding_avg":
        sfx = f"sliding_i{GRASS_SLIDING_ITERATIONS}_s{int(GRASS_SLIDING_SLIDE*10)}"
    elif method == "douglas+sliding_avg":
        dp  = int(round(GRASS_DOUGLAS_THRESHOLD))
        sfx = f"dp{dp}_sliding_i{GRASS_SLIDING_ITERATIONS}_s{int(GRASS_SLIDING_SLIDE*10)}"
    else:
        dp  = int(round(GRASS_DOUGLAS_THRESHOLD))
        ch  = int(round(GRASS_CHAIKEN_THRESHOLD))
        sfx = f"dp{dp}_chaiken_t{ch}"

    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 7+8 (GRASS): r.external→r.patch→r.to.vect→v.generalize→v.out.ogr")
    log.info("Källmapp : %s", gen6_dir)
    log.info("Utmapp   : %s", output_dir)
    log.info("Metod    : %s  (tröskel dp=%.1f m)", method, GRASS_DOUGLAS_THRESHOLD)
    log.info("══════════════════════════════════════════════════════════")

    if not gen6_dir.exists():
        log.error("Källkatalog saknas (%s) — kör steg 6 (och ev. 6b) först", gen6_dir.name)
        sys.exit(1)

    # ── Hitta alla varianter att processa ─────────────────────────────────
    # MORPH_ONLY=True: bara *_morph_*-mappar. Annars också conn4, conn8, majority.
    # Om MORPH_SMOOTH_METHOD="none" finns inga morph-mappar — kör alla varianter.
    subdirs = sorted(d for d in gen6_dir.iterdir() if d.is_dir())
    if MORPH_ONLY and MORPH_SMOOTH_METHOD != "none":
        subdirs = [d for d in subdirs if "_morph_" in d.name]

    if not subdirs:
        log.error("Inga undermappar hittades i %s", gen6_dir)
        sys.exit(1)

    ok_count = 0
    for subdir in subdirs:
        tifs = sorted(subdir.glob("*.tif"))
        if not tifs:
            log.warning("  %s: inga TIF-filer, hoppar över", subdir.name)
            continue

        variant_name = subdir.name          # t.ex. 'conn4_morph_disk_r02'
        out_gpkg = output_dir / f"{variant_name}_{sfx}.gpkg"

        log.info("")
        log.info("%s", variant_name.upper())

        if out_gpkg.exists():
            log.info("  Hoppar över %s — GPKG finns redan", out_gpkg.name)
            ok_count += 1
            continue

        # ── Chunked GRASS-körning med halo (som steg 6) ───────────────────
        # Om GRASS_CHUNK_TILE_ROWS > 0:
        #   1. Dela tile-raderna i chunks om GRASS_CHUNK_TILE_ROWS rader.
        #   2. Ge varje chunk GRASS_CHUNK_OVERLAP extra halo-rader ovanför/nedanför.
        #   3. Kör GRASS på chunk+halo → chunk_raw.gpkg.
        #   4. Klipp med ogr2ogr -clipsrc till de ägda radernas exakta bbox
        #      → chunk_clip.gpkg. Polygoner vid sömmen ser full kontext → inga
        #      topologiska artefakter längs chunksömmen.
        #   5. Slå ihop alla klippta chunks till slutfilen.
        # Om GRASS_CHUNK_TILE_ROWS == 0: kör alla TIF:er i en enda session.
        if GRASS_CHUNK_TILE_ROWS > 0:
            import re as _re
            import json as _json

            # Geotransform från källrastret för exakta Y-koordinater
            _gi = subprocess.run(
                ["gdalinfo", "-json", str(SRC)],
                capture_output=True, text=True
            )
            _gt = _json.loads(_gi.stdout)["geoTransform"]
            _y_origin = _gt[3]
            _px_h     = abs(_gt[5])
            _tile_h   = TILE_SIZE * _px_h   # m per tile-rad

            # Extrahera rad- och kolumnnummer ur filnamn (tile_r043_c016_...)
            def _row_of(p):
                m = _re.search(r'_r(\d+)_', p.name)
                return int(m.group(1)) if m else 0

            def _col_of(p):
                m = _re.search(r'_c(\d+)[_.]', p.name)
                return int(m.group(1)) if m else 0

            all_tile_rows = sorted(set(_row_of(t) for t in tifs))
            all_tile_cols = sorted(set(_col_of(t) for t in tifs))
            n_rows = len(all_tile_rows)

            # X-extent täcker alla kolumner (klippning sker bara i Y)
            _px_w = _gt[1]
            _tile_w = TILE_SIZE * _px_w
            x_min = _gt[0] + all_tile_cols[0]  * _tile_w
            x_max = _gt[0] + (all_tile_cols[-1] + 1) * _tile_w

            # Bygg chunks med överlapp
            chunk_owned = [
                all_tile_rows[i : i + GRASS_CHUNK_TILE_ROWS]
                for i in range(0, n_rows, GRASS_CHUNK_TILE_ROWS)
            ]
            log.info("  Chunked GRASS m. halo: %d tile-rader → %d chunk(s) "
                     "à max %d rader, halo ±%d rader",
                     n_rows, len(chunk_owned), GRASS_CHUNK_TILE_ROWS, GRASS_CHUNK_OVERLAP)

            chunk_clip_gpkgs = []
            all_ok = True
            for ci, owned_rows in enumerate(chunk_owned):
                chunk_label = f"{variant_name}_chunk{ci:03d}"
                chunk_raw_gpkg  = output_dir / f"{chunk_label}_{sfx}_raw.gpkg"
                chunk_clip_gpkg = output_dir / f"{chunk_label}_{sfx}.gpkg"

                if chunk_clip_gpkg.exists():
                    log.info("  Chunk %d/%d: hoppar över — klippt GPKG finns",
                             ci + 1, len(chunk_owned))
                    chunk_clip_gpkgs.append(chunk_clip_gpkg)
                    continue

                # Bygg halo: owned_rows ± GRASS_CHUNK_OVERLAP rader
                first_idx = all_tile_rows.index(owned_rows[0])
                last_idx  = all_tile_rows.index(owned_rows[-1])
                ov_start  = max(0, first_idx - GRASS_CHUNK_OVERLAP)
                ov_end    = min(n_rows - 1, last_idx + GRASS_CHUNK_OVERLAP)
                halo_row_set = set(all_tile_rows[ov_start : ov_end + 1])
                chunk_tifs   = [t for t in tifs if _row_of(t) in halo_row_set]

                log.info("  Chunk %d/%d: ägda rader %d–%d, halo %d–%d (%d TIF:er)",
                         ci + 1, len(chunk_owned),
                         owned_rows[0], owned_rows[-1],
                         all_tile_rows[ov_start], all_tile_rows[ov_end],
                         len(chunk_tifs))

                # Kör GRASS på chunk+halo
                if not chunk_raw_gpkg.exists():
                    ok = _run_grass_78(
                        tif_files=chunk_tifs,
                        variant_name=variant_name,
                        output_gpkg=chunk_raw_gpkg,
                        method=method,
                        douglas_threshold=GRASS_DOUGLAS_THRESHOLD,
                        chaiken_threshold=GRASS_CHAIKEN_THRESHOLD,
                        log=log,
                        checkpoint_prefix=chunk_label,
                    )
                    if not ok:
                        log.error("  Chunk %d/%d GRASS misslyckades", ci + 1, len(chunk_owned))
                        all_ok = False
                        break

                # Klipp tillbaka till ägda raders exakta Y-bbox
                owned_y_max = _y_origin - owned_rows[0]       * _tile_h
                owned_y_min = _y_origin - (owned_rows[-1] + 1) * _tile_h
                clip_wkt = (
                    f"POLYGON(({x_min} {owned_y_min},"
                    f"{x_max} {owned_y_min},"
                    f"{x_max} {owned_y_max},"
                    f"{x_min} {owned_y_max},"
                    f"{x_min} {owned_y_min}))"
                )
                r_clip = subprocess.run([
                    "ogr2ogr", "-f", "GPKG",
                    "-clipsrc", clip_wkt,
                    "-nln", variant_name,
                    str(chunk_clip_gpkg), str(chunk_raw_gpkg)
                ], capture_output=True, text=True)

                chunk_raw_gpkg.unlink(missing_ok=True)  # råfilen behövs inte mer

                if r_clip.returncode != 0 or not chunk_clip_gpkg.exists():
                    log.error("  Chunk %d/%d: klippning misslyckades: %s",
                              ci + 1, len(chunk_owned), r_clip.stderr[:200])
                    all_ok = False
                    break

                chunk_clip_gpkgs.append(chunk_clip_gpkg)

            if not all_ok or not chunk_clip_gpkgs:
                log.error("Misslyckades (chunked+halo) för variant: %s", variant_name)
                continue

            # Slå ihop alla klippta chunks till slutfilen
            log.info("  Slår ihop %d klippta chunk(s) → %s ...",
                     len(chunk_clip_gpkgs), out_gpkg.name)
            merge_ok = True
            for i, cgpkg in enumerate(chunk_clip_gpkgs):
                cmd = ["ogr2ogr", "-f", "GPKG",
                       "-nln", variant_name,
                       str(out_gpkg), str(cgpkg)]
                if i > 0:
                    cmd.insert(3, "-append")
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    log.error("  Merge chunk %d misslyckades: %s", i, r.stderr[:200])
                    merge_ok = False
                    break

            if not merge_ok:
                out_gpkg.unlink(missing_ok=True)
                log.error("Misslyckades (merge) för variant: %s", variant_name)
                continue

            # Städa bort temporära klippta chunks
            for cgpkg in chunk_clip_gpkgs:
                cgpkg.unlink(missing_ok=True)

            sz = out_gpkg.stat().st_size / 1024**2
            log.info("  ✓ %s (%.1f MB, %d chunks)",
                     out_gpkg.name, sz, len(chunk_clip_gpkgs))
            ok_count += 1

        else:
            # ── En enda GRASS-session (originalbet.ende) ───────────────────
            success = _run_grass_78(
                tif_files=tifs,
                variant_name=variant_name,
                output_gpkg=out_gpkg,
                method=method,
                douglas_threshold=GRASS_DOUGLAS_THRESHOLD,
                chaiken_threshold=GRASS_CHAIKEN_THRESHOLD,
                log=log,
            )
            if success:
                ok_count += 1
            else:
                log.error("Misslyckades för variant: %s", variant_name)

    elapsed_total = time.time() - t_start
    log.info("")
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 7+8 klar: %d/%d varianter OK  (%.1f min)", ok_count, len(subdirs), elapsed_total / 60)
    log.info("══════════════════════════════════════════════════════════")

    if ok_count == 0:
        sys.exit(1)
