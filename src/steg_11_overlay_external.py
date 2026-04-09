"""
steg_11_overlay_external.py — Steg 11: Lägg extern vektorfil ovanpå det merged lagret.

Läser merged GPKG per variant från steg_10_merge/ och klipper bort vattenpolygonerna
med Shapely difference + Fiona streaming:

  steg_11_overlay_external/{variant}.gpkg

Approach:
  - Vattenpolygonerna (~420K, ~200MB) läses in en gång per zon och indexeras med STRtree.
  - Markpolygonerna streamas feature-för-feature via Fiona — ingen hel-fils-RAM-last.
  - Per markpolygon: unary_union av överlappande vattenpolygoner → shapely.difference().
  - 0.5m buffer på markpolygoner inför difference för att täta generaliseringsluckor.
  - Zoner körs parallellt med ProcessPoolExecutor (4 processer simultant).

Krasch-robusthet via zoner + persistent work-dir:
  - Varje variant delas in i N_ZONES geografiska Y-zoner.
  - Var zon skriver land_cut_{zon}.gpkg till steg_11_work/{variant}/.
  - Om en zon redan finns hoppas den automatiskt över vid omstart.
  - Sista steget mergar alla zoner + vatten till slutlig GPKG.

Kör: python3 src/steg_11_overlay_external.py
"""

import logging
import multiprocessing
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import fiona
import geopandas as gpd
import pandas as pd
from shapely.geometry import box as shapely_box, Polygon, MultiPolygon
from shapely import wkb as shapely_wkb

from config import (OUT_BASE, OVERLAY_EXTERNAL_PATH, OVERLAY_EXTERNAL_CLASS,
                    OVERLAY_EXTERNAL_LAYER, GRASS_VECTOR_MEMORY, GRASS_OMP_THREADS,
                    VECTOR_MIN_AREA_M2, VECTOR_FILL_HOLE_M2)

LN = "markslag"
# Buffer på markpolygoner inför difference: tätar generaliseringsluckor mot vattengränser
# OBS: Steg 6b (expand_water) hanterar redan mikrogapen med EXPAND_WATER_PX px inåt i vatten,
# och GRASS_SNAP_TOLERANCE=0.5m snappar topologin. En positiv buffer här expanderar marken
# även MOT grannlandpolygoner → 0.5m överlapp → dubbla konturer längs mark-mark-gränser.
_LAND_BUFFER_M = 0
# Antal zoner (geografiska Y-band) — fler zoner = mindre RAM per worker
N_ZONES = 20
# Antal parallella processer — begränsas av RAM (varje worker laddar ~420K vattenpolygoner)
# 8 workers × ~5 GB/worker ≈ 40 GB → säkert inom 54 GB
ZONE_WORKERS = 8


def setup_logging(out_base):
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_num  = os.getenv("STEP_NUMBER", "11")
    step_name = os.getenv("STEP_NAME", "overlay_external").lower()
    step_suffix = f"steg_{step_num}_{step_name}_{ts}"
    fmt_detail = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_summary = logging.Formatter(
        "%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S"
    )
    log = logging.getLogger("pipeline.overlay_external")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.handlers.clear()
    dbg = logging.FileHandler(str(log_dir / f"debug_{step_suffix}.log"))
    dbg.setLevel(logging.DEBUG); dbg.setFormatter(fmt_detail); log.addHandler(dbg)
    fh = logging.FileHandler(str(summary_dir / f"summary_{step_suffix}.log"))
    fh.setLevel(logging.INFO); fh.setFormatter(fmt_summary); log.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO); ch.setFormatter(fmt_summary); log.addHandler(ch)
    return log


def load_external(path: Path, target_crs, log) -> gpd.GeoDataFrame:
    """Läser den externa vektorfilen, reprojecterar vid behov och sätter klassvärde."""
    if OVERLAY_EXTERNAL_LAYER is None:
        layers = [None]
    elif isinstance(OVERLAY_EXTERNAL_LAYER, str):
        layers = [OVERLAY_EXTERNAL_LAYER]
    else:
        layers = list(OVERLAY_EXTERNAL_LAYER)

    gdfs = []
    for layer in layers:
        log.info("  Läser lager: %s från %s", layer or "(första)", path)
        read_kwargs = {"filename": str(path)}
        if layer is not None:
            read_kwargs["layer"] = layer
        gdf_part = gpd.read_file(**read_kwargs)
        log.info("    %d polygoner inlästa, CRS: %s", len(gdf_part), gdf_part.crs)
        gdfs.append(gdf_part)

    gdf = pd.concat(gdfs, ignore_index=True) if len(gdfs) > 1 else gdfs[0]
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry")
    log.info("  Totalt %d polygoner (lager: %s)", len(gdf),
             ", ".join(str(l) for l in layers))

    if gdf.crs is None:
        log.warning("  Extern fil saknar CRS — antar att den matchar mållagret")
    elif gdf.crs != target_crs:
        log.info("  Reprojecterar %s → %s", gdf.crs, target_crs)
        gdf = gdf.to_crs(target_crs)

    if OVERLAY_EXTERNAL_CLASS is not None:
        gdf[LN] = OVERLAY_EXTERNAL_CLASS
    elif LN not in gdf.columns:
        log.warning("  Kolumnen '%s' saknas i extern fil — fyller med 0", LN)
        gdf[LN] = 0

    return gdf[["geometry", LN]].copy()


def _fill_small_holes(gdf: gpd.GeoDataFrame, min_area_m2: float, log) -> gpd.GeoDataFrame:
    """Fyller hål (interior rings) < min_area_m2 i vattenpolygonerna."""
    if min_area_m2 <= 0:
        return gdf

    def _fill(geom):
        if geom.geom_type == "Polygon":
            kept = [ring for ring in geom.interiors if Polygon(ring).area >= min_area_m2]
            return Polygon(geom.exterior, kept)
        if geom.geom_type == "MultiPolygon":
            return MultiPolygon([_fill(p) for p in geom.geoms])
        return geom

    n_holes_before = sum(
        len(list(g.interiors)) if g.geom_type == "Polygon"
        else sum(len(list(p.interiors)) for p in g.geoms) if g.geom_type == "MultiPolygon"
        else 0
        for g in gdf.geometry
    )
    gdf = gdf.copy()
    gdf[gdf.geometry.name] = gdf.geometry.apply(_fill)
    n_holes_after = sum(
        len(list(g.interiors)) if g.geom_type == "Polygon"
        else sum(len(list(p.interiors)) for p in g.geoms) if g.geom_type == "MultiPolygon"
        else 0
        for g in gdf.geometry
    )
    filled = n_holes_before - n_holes_after
    if filled:
        log.info("    Fyllde %d hål < %.0f m² i externa vattenpolygoner", filled, min_area_m2)
    return gdf


def _get_gpkg_bounds(gpkg: Path) -> tuple | None:
    """Returnerar (x_min, y_min, x_max, y_max) via ogrinfo utan att läsa data."""
    import re as _re
    r = subprocess.run(["ogrinfo", "-al", "-so", str(gpkg)],
                       capture_output=True, text=True)
    m = _re.search(
        r'Extent:\s*\(([^,]+),\s*([^)]+)\)\s*-\s*\(([^,]+),\s*([^)]+)\)', r.stdout)
    if not m:
        return None
    return tuple(float(v) for v in m.groups())  # x_min, y_min, x_max, y_max


def _get_gpkg_crs(gpkg: Path):
    """Returnerar CRS via geopandas sample-läsning (1 rad)."""
    return gpd.read_file(str(gpkg), rows=1).crs


def _zone_n_features(gpkg: Path, x_min, z_y_min, x_max, z_y_max) -> int:
    """Räknar features i en spatialt begrän rad zon via ogrinfo."""
    import re as _re
    r = subprocess.run([
        "ogrinfo", "-al", "-so",
        "-spat", f"{x_min:.2f}", f"{z_y_min:.2f}", f"{x_max:.2f}", f"{z_y_max:.2f}",
        str(gpkg),
    ], capture_output=True, text=True)
    m = _re.search(r'Feature Count:\s*(\d+)', r.stdout)
    return int(m.group(1)) if m else -1


def _process_zone_worker(args):
    """Toppfunktion för ProcessPoolExecutor — unpacker args-tuple och kör _process_zone_impl."""
    return _process_zone_impl(*args)


def _process_zone_impl(
    zone_idx: int, n_zones: int,
    x_min: float, y_min_all: float, x_max: float, y_max_all: float,
    land_tmp_str: str, water_geoms_data: list, water_lns: list,
    variant: str, work_dir_str: str,
    min_area_m2: float,
) -> tuple[int, bool, str]:
    """Kör Shapely difference för en geografisk zon i en separat process.

    Tar emot land_tmp-sökväg (redan extraherad av process_variant) och
    vattengeometrier som WKB-bytes (pickle-vänligt).
    Returnerar (zone_idx, ok, meddelande).
    """
    import fiona
    from shapely.geometry import shape, mapping, MultiPolygon
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    from shapely import wkb as shapely_wkb

    work_dir = Path(work_dir_str)
    land_tmp = Path(land_tmp_str)

    cut_gpkg = work_dir / f"land_cut_{zone_idx:03d}.gpkg"
    if cut_gpkg.exists() and cut_gpkg.stat().st_size > 500_000:
        return zone_idx, True, f"Zon {zone_idx+1}/{n_zones}: checkpoint finns — hoppar"

    zone_h = (y_max_all - y_min_all) / n_zones
    z_y_min = y_min_all + zone_idx * zone_h
    z_y_max = y_min_all + (zone_idx + 1) * zone_h

    # Deserialisera vattengeometrier från WKB
    water_geoms = [shapely_wkb.loads(wkb) for wkb in water_geoms_data]

    # Bygg STRtree på ALLA vattenpolygoner — krävs för att täcka landpolygoner
    # vars centroid är i denna zon men vars kropp sträcker sig in i angränsande zoner.
    water_tree = STRtree(water_geoms)

    # Läs schema från land_tmp
    with fiona.open(str(land_tmp)) as lds:
        src_schema = lds.schema.copy()
        src_crs = lds.crs
        n_total = len(lds)

    # Sätt geometry type till Unknown så att både Polygon och MultiPolygon accepteras
    # (difference() kan returnera MultiPolygon även om källan är Polygon)
    src_schema["geometry"] = "Unknown"

    # Marklagret kanske saknar markslag-kolumnen — lägg till om det saknas
    has_ln_in_source = LN in src_schema["properties"]
    if not has_ln_in_source:
        src_schema["properties"][LN] = "int"

    t0 = time.time()
    n_kept = n_clipped = n_dropped = 0
    tmp_gpkg = Path(str(cut_gpkg) + ".tmp.gpkg")
    tmp_gpkg.unlink(missing_ok=True)

    with fiona.open(str(land_tmp)) as lds, \
         fiona.open(str(tmp_gpkg), "w", driver="GPKG",
                    schema=src_schema, crs=src_crs, layer="land_cut") as dst:
        for i, feat in enumerate(lds):
            geom = shape(feat.geometry)
            if geom is None or geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)

            # Tilldela varje polygon till exakt en zon via centroidens Y-koordinat.
            # Undviker klippning av polygoner vid zonsgränser (inga sömsartefakter).
            cy = geom.centroid.y
            if zone_idx < n_zones - 1:
                if not (z_y_min <= cy < z_y_max):
                    continue
            else:  # sista zon: inkludera allt med cy >= z_y_min
                if cy < z_y_min:
                    continue

            geom_buf = geom.buffer(_LAND_BUFFER_M) if _LAND_BUFFER_M > 0 else geom
            cands = water_tree.query(geom_buf, predicate="intersects")

            props = dict(feat.properties)
            if not has_ln_in_source:
                props[LN] = 0

            if len(cands) == 0:
                dst.write({"geometry": mapping(geom), "properties": props})
                n_kept += 1
                continue

            water_union = unary_union([water_geoms[c] for c in cands])
            try:
                cut = geom_buf.difference(water_union)
            except Exception:
                try:
                    cut = geom_buf.buffer(0).difference(water_union.buffer(0))
                except Exception:
                    cut = geom

            if cut.is_empty:
                n_dropped += 1
                continue

            if min_area_m2 > 0:
                if cut.geom_type == "Polygon":
                    if cut.area < min_area_m2:
                        n_dropped += 1
                        continue
                elif cut.geom_type == "MultiPolygon":
                    parts = [p for p in cut.geoms if p.area >= min_area_m2]
                    if not parts:
                        n_dropped += 1
                        continue
                    cut = parts[0] if len(parts) == 1 else MultiPolygon(parts)
                elif cut.geom_type == "GeometryCollection":
                    parts = [p for p in cut.geoms
                             if p.geom_type in ("Polygon", "MultiPolygon") and p.area >= min_area_m2]
                    if not parts:
                        n_dropped += 1
                        continue
                    cut = parts[0] if len(parts) == 1 else unary_union(parts)

            dst.write({"geometry": mapping(cut), "properties": props})
            n_clipped += 1

    elapsed = time.time() - t0
    tmp_gpkg.rename(cut_gpkg)
    summary = (f"Zon {zone_idx+1}/{n_zones}: {n_kept} oförändrade, {n_clipped} klippta, "
               f"{n_dropped} borttagna  ({elapsed/60:.1f} min)")
    return zone_idx, True, summary


def _postprocess_cut(cut_gpkg: Path, log) -> bool:
    """Städar kolumnnamn i land_cut GPKG på disk med ogr2ogr SQL (ingen minneslast).

    v.overlay prefixar kolumner med 'a_' — vi döper om och tar bort b_-kolumner.
    Skriver resultatet till {cut_gpkg}.clean och byter sedan ut originalet.
    """
    import re as _re2
    r = subprocess.run(["ogrinfo", "-al", "-so", str(cut_gpkg)],
                       capture_output=True, text=True)
    # Hämta kolumnnamn
    cols = _re2.findall(r'^\s+(\w+): \w+', r.stdout, _re2.MULTILINE)
    cols = [c for c in cols if c.lower() not in ("fid",)]

    rename_sql_parts = []
    keep_cols = []
    for c in cols:
        if c.startswith("a_"):
            new_name = c[2:]
            rename_sql_parts.append(f'"{c}" AS "{new_name}"')
            keep_cols.append(new_name)
        elif c.startswith("b_") or c in ("cat", "cat_", "label", "DN"):
            continue
        else:
            rename_sql_parts.append(f'"{c}"')
            keep_cols.append(c)

    if not rename_sql_parts:
        return True  # inget att göra

    # Se till LN finns
    if LN not in keep_cols:
        rename_sql_parts.append(f'0 AS "{LN}"')

    layer = "land_cut"
    sql = f'SELECT geometry, {", ".join(rename_sql_parts)} FROM "{layer}"'
    clean_gpkg = Path(str(cut_gpkg) + ".clean.gpkg")
    r2 = subprocess.run([
        "ogr2ogr", "-f", "GPKG", "-dialect", "SQLite", "-sql", sql,
        "-nln", layer,
        str(clean_gpkg), str(cut_gpkg),
    ], capture_output=True, text=True)
    if r2.returncode != 0:
        log.warning("  postprocess SQL misslyckades för %s: %s", cut_gpkg.name, r2.stderr[:200])
        return False
    cut_gpkg.unlink()
    clean_gpkg.rename(cut_gpkg)
    return True


def process_variant(gpkg: Path, ext_path: Path, out_dir: Path, work_base: Path, log,
                    mem_mb: int, omp_threads: int, n_zones: int = 4) -> bool:
    """Shapely difference per geografisk zon, parallellt med ProcessPoolExecutor.

    Laddar ALDRIG hela variant-GPKG i Python-minnet i huvudprocessen.
    Varje zon extraheras med ogr2ogr -spat/-clipsrc i separata processer.
    Checkpoint: land_cut_{zon}.gpkg i work_dir överlever krasch.
    """
    variant = gpkg.stem
    out_gpkg = out_dir / gpkg.name

    if out_gpkg.exists():
        log.info("  Hoppar över %s — slutfil finns redan", gpkg.name)
        return True

    work_dir = work_base / variant
    work_dir.mkdir(parents=True, exist_ok=True)

    # Hämta extent och CRS utan att ladda hela filen
    log.info("  Hämtar extent för %s...", gpkg.name)
    bounds = _get_gpkg_bounds(gpkg)
    if bounds is None:
        log.error("  Kan inte läsa bounds från %s", gpkg.name)
        return False
    x_min, y_min_all, x_max, y_max_all = bounds
    crs = _get_gpkg_crs(gpkg)
    log.info("    Extent: (%.0f, %.0f) - (%.0f, %.0f)  CRS: %s",
             x_min, y_min_all, x_max, y_max_all, crs)

    # Läs extern vattenfil (~200 MB — OK i minne)
    ext_gdf = load_external(ext_path, crs, log)
    landscape_bbox = shapely_box(x_min, y_min_all, x_max, y_max_all)
    n_before = len(ext_gdf)
    ext_gdf = gpd.clip(ext_gdf, landscape_bbox)
    log.info("    %d externa polygoner inom extent (var %d totalt)", len(ext_gdf), n_before)
    ext_gdf = _fill_small_holes(ext_gdf, VECTOR_FILL_HOLE_M2, log)

    if ext_gdf.empty:
        log.info("    Inga externa polygoner — kopierar GPKG oförändrad")
        shutil.copy2(str(gpkg), str(out_gpkg))
        return True

    # Serialisera vattengeometrier till WKB för pickle-säker överföring till subprocesser
    from shapely import wkb as shapely_wkb
    water_geoms_wkb = [shapely_wkb.dumps(g) for g in ext_gdf.geometry]
    water_lns = list(ext_gdf[LN].astype(int))
    log.info("    %d vattenpolygoner serialiserade för processar", len(water_geoms_wkb))

    # Fas 1: Extrahera alla zoner sekventiellt med ogr2ogr (undviker SQLite-konflikter
    # vid parallell läsning från samma 22 GB källfil)
    zone_h = (y_max_all - y_min_all) / n_zones
    land_tmps = []
    for zone_idx in range(n_zones):
        z_y_min = y_min_all + zone_idx * zone_h
        z_y_max = y_min_all + (zone_idx + 1) * zone_h
        if zone_idx == n_zones - 1:
            z_y_max = y_max_all + 1.0
        land_tmp = work_dir / f"land_{zone_idx:03d}.gpkg"
        cut_chk  = work_dir / f"land_cut_{zone_idx:03d}.gpkg"
        # Skippa extraktion om checkpoint redan finns
        if cut_chk.exists() and cut_chk.stat().st_size > 500_000:
            land_tmps.append(land_tmp)
            log.info("    Zon %d/%d: checkpoint finns — hoppar extraktion", zone_idx + 1, n_zones)
            continue
        if land_tmp.exists() and land_tmp.stat().st_size < 500_000:
            land_tmp.unlink()
        if not land_tmp.exists():
            log.info("    Zon %d/%d: ogr2ogr extraktion...", zone_idx + 1, n_zones)
            r = subprocess.run([
                "ogr2ogr", "-f", "GPKG", "-overwrite",
                "-spat", f"{x_min:.2f}", f"{z_y_min:.2f}", f"{x_max:.2f}", f"{z_y_max:.2f}",
                "-nln", "land",
                str(land_tmp), str(gpkg),
            ], capture_output=True, text=True)
            if r.returncode != 0:
                log.error("  ogr2ogr zon %d misslyckades: %s", zone_idx + 1, r.stderr[:300])
                return False
            log.info("    Zon %d/%d: extraktion klar (%s)",
                     zone_idx + 1, n_zones, land_tmp.name)
        land_tmps.append(land_tmp)

    # Fas 2: Kör Shapely difference parallellt
    cut_parts = [None] * n_zones
    failed = False

    zone_args = [
        (
            zone_idx, n_zones,
            x_min, y_min_all, x_max, y_max_all,
            str(land_tmps[zone_idx]), water_geoms_wkb, water_lns,
            variant, str(work_dir),
            VECTOR_MIN_AREA_M2,
        )
        for zone_idx in range(n_zones)
    ]

    with ProcessPoolExecutor(max_workers=ZONE_WORKERS) as ex:
        futs = {ex.submit(_process_zone_worker, args): args[0] for args in zone_args}
        for fut in as_completed(futs):
            zi = futs[fut]
            try:
                zone_idx_ret, ok, msg = fut.result()
            except Exception as exc:
                log.error("  Zon %d kraschade: %s", zi + 1, exc)
                failed = True
                continue
            log.info("    %s", msg)
            if not ok:
                log.error("  Zon %d misslyckades — avbryter %s", zi + 1, gpkg.name)
                failed = True
            else:
                cut_gpkg = work_dir / f"land_cut_{zone_idx_ret:03d}.gpkg"
                cut_parts[zone_idx_ret] = cut_gpkg

    if failed:
        return False

    # Merga alla zoner + vatten med ogr2ogr -append
    log.info("  Mergar %d zoner...", n_zones)
    merged_tmp = work_dir / "merged_land.gpkg"
    if merged_tmp.exists():
        merged_tmp.unlink()

    first = True
    for part in cut_parts:
        if part is None or not part.exists() or part.stat().st_size == 0:
            continue
        cmd = ["ogr2ogr", "-f", "GPKG", "-nln", variant]
        if not first:
            cmd += ["-append", "-update"]
        cmd += [str(merged_tmp), str(part), "land_cut"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log.error("  merge zon %s: %s", part.name, r.stderr[:300])
            return False
        first = False

    # Lägg till vattenpolygoner
    zone_h = (y_max_all - y_min_all) / n_zones
    for zone_idx in range(n_zones):
        z_y_min = y_min_all + zone_idx * zone_h
        z_y_max = y_min_all + (zone_idx + 1) * zone_h
        if zone_idx == n_zones - 1:
            z_y_max = y_max_all + 1.0
        zone_bbox = shapely_box(x_min - 1, z_y_min - 1, x_max + 1, z_y_max + 1)
        water_zone = ext_gdf[ext_gdf.geometry.intersects(zone_bbox)].copy()
        if water_zone.empty:
            continue
        water_tmp2 = work_dir / f"water_final_{zone_idx:03d}.gpkg"
        water_zone[[LN, "geometry"]].to_file(str(water_tmp2), driver="GPKG", layer=variant)
        r = subprocess.run([
            "ogr2ogr", "-f", "GPKG", "-nln", variant, "-append", "-update",
            str(merged_tmp), str(water_tmp2),
        ], capture_output=True, text=True)
        if r.returncode != 0:
            log.warning("  vatten zon %d: %s", zone_idx, r.stderr[:200])

    shutil.copy2(str(merged_tmp), str(out_gpkg))
    sz = out_gpkg.stat().st_size / 1e6
    log.info("  ✓ %s — %.1f MB", out_gpkg.name, sz)
    return True


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)

    log = setup_logging(OUT_BASE)
    t0 = time.time()

    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 11: Overlay extern vektorfil på merged lager (zoner)")
    log.info("Källmapp : %s", OUT_BASE / "steg_10_merge")
    log.info("Utmapp   : %s", OUT_BASE / "steg_11_overlay_external")
    log.info("Work-dir : %s", OUT_BASE / "steg_11_work")
    log.info("══════════════════════════════════════════════════════════")

    if not OVERLAY_EXTERNAL_PATH:
        log.error("OVERLAY_EXTERNAL_PATH är inte satt i config.py — avslutar")
        sys.exit(1)

    ext_path = Path(OVERLAY_EXTERNAL_PATH)
    if not ext_path.exists():
        log.error("Extern fil saknas: %s", ext_path)
        sys.exit(1)

    src_dir = OUT_BASE / "steg_10_merge"
    if not src_dir.exists():
        log.error("steg_10_merge/ saknas — kör steg 10 först")
        sys.exit(1)

    out_dir = OUT_BASE / "steg_11_overlay_external"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_base = OUT_BASE / "steg_11_work"
    work_base.mkdir(parents=True, exist_ok=True)

    gpkgs = sorted(src_dir.glob("*.gpkg"))
    if not gpkgs:
        log.error("Inga GPKG-filer i %s", src_dir)
        sys.exit(1)

    layers_label = OVERLAY_EXTERNAL_LAYER or "(första lagret)"
    if isinstance(layers_label, list):
        layers_label = ", ".join(layers_label)
    log.info("Extern fil   : %s", ext_path)
    log.info("Lager        : %s", layers_label)
    log.info("Varianter    : %d st (%s)", len(gpkgs), ", ".join(g.stem for g in gpkgs))
    log.info("Zoner        : %d geografiska Y-zoner per variant, %d parallellt", N_ZONES, ZONE_WORKERS)
    if OVERLAY_EXTERNAL_CLASS is not None:
        log.info("Klass        : %d (OVERLAY_EXTERNAL_CLASS)", OVERLAY_EXTERNAL_CLASS)
    else:
        log.info("Klass        : läses från extern fils 'markslag'-kolumn")
    log.info("Approach     : Fiona streaming + Shapely difference (ingen GRASS)")
    log.info("Mark-buffer  : %.1f m (tätar generaliseringsluckor)", _LAND_BUFFER_M)
    log.info("═" * 58)

    ok_count = 0
    for gpkg in gpkgs:
        if process_variant(gpkg, ext_path, out_dir, work_base, log,
                           GRASS_VECTOR_MEMORY, GRASS_OMP_THREADS, N_ZONES):
            ok_count += 1

    elapsed = time.time() - t0
    log.info("")
    log.info("═" * 58)
    log.info("Steg 11 klart — %d/%d varianter  %.1f min (%.0fs)",
             ok_count, len(gpkgs), elapsed / 60, elapsed)
    log.info("Output i %s", out_dir)
    log.info("═" * 58)
