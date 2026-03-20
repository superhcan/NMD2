#!/usr/bin/env python3
"""
run_test_4tiles_v8.py — Kör pipelinen på 4 test-tiles, steg 2-9
(Hoppar över steg 1 som skulle läsa originalbilden — tiles kopieras från v8)
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

out_base = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8b")
os.environ["OUT_BASE"] = str(out_base)

# Kopiera steg1-tiles från v8 (identiska tiles, undviker att läsa rasteroriginal)
v8_tiles = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8/steg1_tiles")
v8b_tiles = out_base / "steg1_tiles"
if not v8b_tiles.exists():
    print(f"Kopierar steg1_tiles från v8 → v8b...")
    shutil.copytree(v8_tiles, v8b_tiles)
    print(f"  Kopierat {len(list(v8b_tiles.iterdir()))} filer")

steps = [
    (2, "steg_2_extract_protected", "Steg 2: Extrahera skyddade klasser"),
    (3, "steg_3_extract_landscape", "Steg 3: Extrahera landskapsbild"),
    (4, "steg_4_filter_lakes", "Steg 4: Ta bort små sjöar"),
    (5, "steg_5_filter_islands", "Steg 5: Fylla landöar omringade av vatten"),
    (6, "steg_6_generalize", "Steg 6: Generalisera"),
    (7, "steg_7_vectorize", "Steg 7: Vektorisera"),
    (8, "steg_8_simplify", "Steg 8: Mapshaper-förenkling"),
    (9, "steg_9_build_qgis_project", "Steg 9: QGIS-projekt"),
]

project_root = Path("/home/hcn/projects/NMD2")
src_dir = project_root / "src"

print("="*70)
print("🧪 PIPELINE TEST - 4 TILES v8b (STEG 2-9)")
print("="*70)
print(f"\nOutput: {out_base}\n")

for step_num, script_name, step_name in steps:
    script_path = src_dir / f"{script_name}.py"

    print(f"\n{'='*70}")
    print(f"🚀 {step_name}")
    print(f"{'='*70}")

    env = os.environ.copy()
    env["STEP_NUMBER"] = str(step_num)
    step_name_short = f"{script_name}.py".replace("steg_", "").replace(".py", "").lower()
    env["STEP_NAME"] = step_name_short

    cmd = ["/home/hcn/projects/NMD2/.venv/bin/python", str(script_path)]
    result = subprocess.run(cmd, cwd=str(project_root), env=env)

    if result.returncode != 0:
        print(f"\n❌ {step_name} MISSLYCKADES")
        sys.exit(1)

print("\n" + "="*70)
print("✅ ALLA STEG KLARA")
print("="*70)
