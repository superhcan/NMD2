#!/usr/bin/env python3
"""
test_4tiles.py — Kör steg 2-8 på bara 4 tiles (2×2 område) för snabb testning.

Test-område: rad 10-11, kolumn 10-11 (4 tiles från ungefär mitten av kartan)
Test-output: /home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles/

Steg 1 hoppas över eftersom tiles redan är förberedda.
Använd för att verifiera att steg 2-8 fungerar innan full körning.
"""

import shutil
import subprocess
import sys
import os
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════

TILES_SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v7/tiles")
TEST_TILES = ["r010_c010", "r010_c011", "r011_c010", "r011_c011"]
TEST_OUT = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_test_4tiles")

# ══════════════════════════════════════════════════════════════════════════════

def setup_test_data():
    """Kopiera 4 test-tiles till testoutput-katalog."""
    print("🔧 Förbereder testdata...")
    
    test_tiles_dir = TEST_OUT / "steg1_tiles"
    test_tiles_dir.mkdir(parents=True, exist_ok=True)
    
    # Rensa gamla test-tiles
    for f in test_tiles_dir.glob("*.tif"):
        f.unlink()
    for f in test_tiles_dir.glob("*.qml"):
        f.unlink()
    
    # Kopiera 4 tiles
    for tile_id in TEST_TILES:
        src_tif = TILES_SRC / f"NMD2023bas_tile_{tile_id}.tif"
        src_qml = TILES_SRC / f"NMD2023bas_tile_{tile_id}.qml"
        dst_tif = test_tiles_dir / f"NMD2023bas_tile_{tile_id}.tif"
        dst_qml = test_tiles_dir / f"NMD2023bas_tile_{tile_id}.qml"
        
        if src_tif.exists():
            shutil.copy(src_tif, dst_tif)
            print(f"  ✓ Kopierade {tile_id}.tif")
        if src_qml.exists():
            shutil.copy(src_qml, dst_qml)
    
    print(f"✓ Testdata klart i {test_tiles_dir}\n")
    return True

def run_all_steps():
    """Kör steg 2-8 på de 4 tiles (steg 1 hoppas över eftersom tiles redan förberedda)."""
    print("🚀 Kör steg 2-8 på 4 tiles...\n")
    print("   (Steg 1 hoppas över – tiles redan förbereda)\n")
    
    # Sätt miljövariabeln för test-output
    env = os.environ.copy()
    env["OUT_BASE"] = str(TEST_OUT)
    
    cmd = [
        sys.executable, "run_all_steps.py",
        "--step", "2", "8"
    ]
    
    print(f"Kommando: {' '.join(cmd)}\n")
    print("=" * 78)
    
    # Kör orchestrator med test-output via miljövariabel
    result = subprocess.run(
        cmd,
        cwd="/home/hcn/projects/NMD2",
        env=env
    )
    
    print("=" * 78)
    return result.returncode == 0

def verify_output():
    """Verifiera att alla steg skapade output."""
    print("\n🔍 Verifierar output...\n")
    
    expected_dirs = [
        "steg1_tiles",
        "steg2_protected",
        "steg3_landscape",
        "steg4_generalized_conn4",
        "steg4_generalized_conn8",
        "steg4_generalized_modal",
        "steg4_generalized_semantic",
        "steg5_filled",
        "steg6_vectorized",
        "steg7_simplified",
        "steg8_qgis_project"
    ]
    
    missing = []
    for d in expected_dirs:
        dir_path = TEST_OUT / d
        if dir_path.exists():
            count = len(list(dir_path.glob("*")))
            print(f"  ✓ {d:30s} ({count} filer)")
        else:
            print(f"  ✗ {d:30s} (SAKNAS)")
            missing.append(d)
    
    if missing:
        print(f"\n⚠️  Saknade katalogerna: {', '.join(missing)}")
        return False
    
    print(f"\n✓ Alla steg producerade output")
    return True

if __name__ == "__main__":
    print("\n" + "=" * 78)
    print("TEST: 4 TILES × 7 STEG")
    print("=" * 78)
    print(f"Test-output: {TEST_OUT}\n")
    
    if not setup_test_data():
        print("❌ Misslyckades förbereda testdata")
        sys.exit(1)
    
    if not run_all_steps():
        print("\n❌ Pipeline misslyckades")
        sys.exit(1)
    
    if not verify_output():
        print("\n⚠️  Pipeline körning slutfördes men några output saknas")
        sys.exit(1)
    
    print("\n" + "=" * 78)
    print("✓ TEST LYCKADES!")
    print("=" * 78)
    print(f"\nTest-resultat finns i: {TEST_OUT}")
    print("\nKöra full pipeline med:")
    print("  cd /home/hcn/projects/NMD2")
    print("  source .venv/bin/activate")
    print("  python3 run_all_steps.py\n")
