#!/usr/bin/env python3
"""
run_test_4tiles_v8.py — Kör pipelinen på 4 test-tiles, steg 2-6
(Hoppar över steg 1 som skulle läsa originalbilden)
"""

import subprocess
import sys
import os
from pathlib import Path

out_base = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles_v8")
os.environ["OUT_BASE"] = str(out_base)

steps = [
    (2, "steg_2_extract_protected", "Steg 2: Extrahera skyddade klasser"),
    (3, "steg_3_extract_landscape", "Steg 3: Extrahera landskapsbild"),
    (4, "steg_4_fill_islands", "Steg 4: Fylla små öar och sjöar"),
    (5, "steg_5_filter_lakes", "Steg 5: Filtrera sjöar"),
    (6, "steg_6_generalize", "Steg 6: Generalisera"),
]

project_root = Path("/home/hcn/projects/NMD2")
src_dir = project_root / "src"

print("="*70)
print("🧪 PIPELINE TEST - 4 TILES (STEG 2-6)")
print("="*70)
print(f"\nOutput: {out_base}\n")

for step_num, script_name, step_name in steps:
    script_path = src_dir / f"{script_name}.py"
    
    print(f"\n{'='*70}")
    print(f"🚀 {step_name}")
    print(f"{'='*70}")
    
    # Sätt miljövaribler för loggning (IDENTISK med run_all_steps.py!)
    env = os.environ.copy()
    env["STEP_NUMBER"] = str(step_num)
    # Samma transformation som run_all_steps.py
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
