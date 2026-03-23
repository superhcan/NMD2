#!/usr/bin/env python3
"""
run_test_4tiles.py — Kör pipelinen på endast 4 testbrickor
Sparar i: /home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_4t_v2/
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

# Sätt miljövariabler för test-körning
out_base = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_4t_v2")
os.environ["OUT_BASE"] = str(out_base)

# De 4 testbrickor som ska användas
test_tiles = [
    "NMD2023bas_tile_r010_c010",
    "NMD2023bas_tile_r010_c011",
    "NMD2023bas_tile_r011_c010",
    "NMD2023bas_tile_r011_c011",
]

print("="*70)
print("🧪 PIPELINE TEST - 4 TILES")
print("="*70)
print(f"\nKör steg 2-6 på dessa 4 testbrickor:")
for tile in test_tiles:
    print(f"  - {tile}.tif")
print(f"\nUtmatning sparas i: {out_base}\n")

# STEG 0: Kopiera testbrickor från tidigare körning
print(f"\n{'='*70}")
print("Förberedelse: Kopiera testbrickor från steg1")
print(f"{'='*70}")

src_tiles_dir = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles/steg1_tiles")
dst_tiles_dir = out_base / "steg1_tiles"
dst_tiles_dir.mkdir(parents=True, exist_ok=True)

if not src_tiles_dir.exists():
    print(f"❌ Källkatalog hittades inte: {src_tiles_dir}")
    sys.exit(1)

# Kopiera endast de 4 testbrickorna
for tile_base in test_tiles:
    tif_file = src_tiles_dir / f"{tile_base}.tif"
    qml_file = src_tiles_dir / f"{tile_base}.qml"
    
    if tif_file.exists():
        shutil.copy2(tif_file, dst_tiles_dir / tif_file.name)
        print(f"  ✓ {tif_file.name}")
    
    if qml_file.exists():
        shutil.copy2(qml_file, dst_tiles_dir / qml_file.name)

print(f"✓ Kopiera testbrickor KLART")

# Steg som ska köras (2-6)
steps = [
    ("steg_2_extract_protected", "Steg 2: Extrahera skyddade klasser"),
    ("steg_3_extract_landscape", "Steg 3: Extrahera landskapsbild"),
    ("steg_4_filter_lakes", "Steg 4: Ta bort små sjöar"),
    ("steg_5_generalize", "Steg 5: Generalisera"),
    ("steg_6_vectorize", "Steg 6: Vektorisera"),
]

project_root = Path("/home/hcn/projects/NMD2")
src_dir = project_root / "src"

for script_name, step_name in steps:
    script_path = src_dir / f"{script_name}.py"
    
    if not script_path.exists():
        print(f"❌ {step_name} - skriptet hittades inte: {script_path}")
        continue
    
    print(f"\n{'='*70}")
    print(f"🚀 {step_name}")
    print(f"{'='*70}")
    
    cmd = ["/home/hcn/projects/NMD2/.venv/bin/python", str(script_path)]
    
    result = subprocess.run(cmd, cwd=str(project_root))
    
    if result.returncode != 0:
        print(f"\n❌ {step_name} MISSLYCKADES")
        sys.exit(1)
    else:
        print(f"\n✓ {step_name} KLART")

print("\n" + "="*70)
print("✅ ALLA STEG KLARA")
print("="*70)
