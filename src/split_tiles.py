"""
Split NMD2023bas_v2_0.tif into tiles.

Namnkonvention: NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif
Varje tile får en kopia av .qml-filen så att QGIS läser in paletten automatiskt.
"""

import shutil
import sys
from pathlib import Path

import rasterio
from rasterio.windows import Window

# ── Inställningar ─────────────────────────────────────────────────────────────
SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.tif")
QML_SRC = SRC.with_suffix(".qml")          # NMD2023bas_v2_0.qml
OUT_DIR = SRC.parent / "tiles"             # .../NMD2023_basskikt_v2_0/tiles/
TILE_SIZE = 2048                            # pixlar per sida
COMPRESS = "lzw"                            # LZW passar bra för klassraster
# ──────────────────────────────────────────────────────────────────────────────

OUT_DIR.mkdir(parents=True, exist_ok=True)

if not QML_SRC.exists():
    print(f"VARNING: Hittade inte {QML_SRC} – palett-filer kopieras inte.")
    copy_qml = False
else:
    copy_qml = True

with rasterio.open(SRC) as src:
    meta = src.meta.copy()
    width = src.width
    height = src.height

    n_cols = (width  + TILE_SIZE - 1) // TILE_SIZE
    n_rows = (height + TILE_SIZE - 1) // TILE_SIZE
    total  = n_rows * n_cols

    print(f"Källbild : {width} × {height} px")
    print(f"Tile-size: {TILE_SIZE} × {TILE_SIZE} px")
    print(f"Tiles    : {n_cols} kolumner × {n_rows} rader = {total} st")
    print(f"Utmapp   : {OUT_DIR}\n")

    count = 0
    for row in range(n_rows):
        for col in range(n_cols):
            x_off = col * TILE_SIZE
            y_off = row * TILE_SIZE
            w     = min(TILE_SIZE, width  - x_off)
            h     = min(TILE_SIZE, height - y_off)

            window    = Window(x_off, y_off, w, h)
            transform = src.window_transform(window)

            tile_name = f"NMD2023bas_tile_r{row:03d}_c{col:03d}.tif"
            tile_path = OUT_DIR / tile_name

            tile_meta = meta.copy()
            tile_meta.update(width=w, height=h, transform=transform,
                             compress=COMPRESS)

            with rasterio.open(tile_path, "w", **tile_meta) as dst:
                dst.write(src.read(window=window))

            # Kopiera QML så QGIS hittar paletten automatiskt
            if copy_qml:
                shutil.copy2(QML_SRC, tile_path.with_suffix(".qml"))

            count += 1
            if count % 50 == 0 or count == total:
                pct = count / total * 100
                print(f"  {count}/{total} ({pct:.0f}%)", flush=True)

print("\nKlart!")
