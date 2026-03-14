#!/usr/bin/env python3
"""
run_all_steps.py — Master orchestrator för NMD2 pipeline.

Kör alla 8 steg i rätt ordning:
  Steg 1: Tileluppdelning (steg_1_split_tiles.py)
  Steg 2: Extrahera skyddade klasser (steg_2_extract_protected.py)
  Steg 3: Extrahera landskapsbild (steg_3_extract_landscape.py)
  Steg 4: Ta bort små områden < 1 ha (steg_4_fill_islands.py)
  Steg 5: Generalisering (steg_5_generalize.py)
  Steg 6: Vektorisering (steg_6_vectorize.py)
  Steg 7: Mapshaper-förenkling (steg_7_simplify.py)
  Steg 8: Bygga QGIS-projekt (steg_8_build_qgis_project.py)

Användning:
  python3 run_all_steps.py              # Kör alla steg
  python3 run_all_steps.py --step 5 8  # Kör endast steg 5-8

Kräver:
  - QGIS (för steg 8)
  - Mapshaper installerat och i PATH
  - Python-venv aktiverad
"""

import logging
import sys
import time
import subprocess
import os
from pathlib import Path
import argparse

# ══════════════════════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

SRC_DIR = Path(__file__).parent / "src"
OUT_BASE = Path(os.getenv("OUT_BASE", "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v7"))

# ══════════════════════════════════════════════════════════════════════════════
# STEG-DEFINITIONER
# ══════════════════════════════════════════════════════════════════════════════

STEPS = {
    1: {
        "name": "Tileluppdelning",
        "script": "steg_1_split_tiles.py",
        "description": "Delar original-raster i 1024×1024 px tiles"
    },
    2: {
        "name": "Extrahera skyddade klasser",
        "script": "steg_2_extract_protected.py",
        "description": "Extraherar vägar, byggnader, vatten som ej ändras",
        "requires_dir": "steg1_tiles"
    },
    3: {
        "name": "Extrahera landskapsbild",
        "script": "steg_3_extract_landscape.py",
        "description": "Ersätter vägar/byggnader med omkringliggande för generalisering",
        "requires_dir": "steg1_tiles"
    },
    4: {
        "name": "Ta bort små områden",
        "script": "steg_4_fill_islands.py",
        "description": "Tar bort alla små områden < 1 ha (öar, sjöar, etc)",
        "requires_dir": "steg3_landscape"
    },
    5: {
        "name": "Generalisering",
        "script": "steg_5_generalize.py",
        "description": "Generaliserar landskapsbild med sieve, modal, semantic och halo-teknik",
        "requires_dir": "steg4_filled"
    },
    6: {
        "name": "Vektorisering",
        "script": "steg_6_vectorize.py",
        "description": "Konverterar generaliserade raster till GeoPackage-vektorer",
        "requires_dir": "steg5_generalized_modal"
    },
    7: {
        "name": "Mapshaper-förenkling",
        "script": "steg_7_simplify.py",
        "description": "Förenklar vektorer med topologi-bevarad Mapshaper",
        "requires_dir": "steg6_vectorized"
    },
    8: {
        "name": "Bygga QGIS-projekt",
        "script": "steg_8_build_qgis_project.py",
        "description": "Bygger QGIS-projekt med alla steg organiserade i grupper",
        "requires_dir": "steg7_simplified"
    }
}

# ══════════════════════════════════════════════════════════════════════════════
# FUNKTIONER
# ══════════════════════════════════════════════════════════════════════════════

def check_requirements():
    """Kontrollera att alla förutsättningar är uppfyllda."""
    log.info("🔍 Kontrollerar förutsättningar...")
    
    # Kontrollera src-katalog
    if not SRC_DIR.exists():
        log.error(f"❌ Kan inte hitta src/ i {SRC_DIR}")
        return False
    
    # Kontrollera config
    if not (SRC_DIR / "config.py").exists():
        log.error("❌ config.py saknas")
        return False
    
    # Kontrollera logging_setup
    if not (SRC_DIR / "logging_setup.py").exists():
        log.error("❌ logging_setup.py saknas")
        return False
    
    log.info("✓ Grundläggande filer OK")
    return True


def check_step_script(step_key):
    """Kontrollera att steg-scriptet finns."""
    script = STEPS[step_key]["script"]
    script_path = SRC_DIR / script
    
    if not script_path.exists():
        log.error(f"❌ Steg {step_key}: {script} saknas i {SRC_DIR}")
        return False
    
    return True


def check_input_directory(step_key):
    """Kontrollera att input-katalogen från föregående steg finns."""
    if "requires_dir" not in STEPS[step_key]:
        return True  # Steg 1 behöver ingen input-katalog
    
    req_dir = STEPS[step_key]["requires_dir"]
    input_path = OUT_BASE / req_dir
    
    if not input_path.exists():
        log.warning(f"⚠️  Steg {step_key}: Input-katalog {req_dir}/ saknas")
        log.warning(f"   Kör föregående steg först eller kontrollera paths")
        return False
    
    return True


def run_step(step_key):
    """Kör ett enskilt steg."""
    step = STEPS[step_key]
    script = step["script"]
    script_path = SRC_DIR / script
    
    log.info("")
    log.info("=" * 78)
    log.info(f"🚀 STEG {step_key}: {step['name']}")
    log.info(f"   {step['description']}")
    log.info("=" * 78)
    
    # Kontroll av script
    if not check_step_script(step_key):
        return False
    
    # Kontroll av input-katalog
    if not check_input_directory(step_key):
        if step.get("optional"):
            log.info(f"⏭️  Hoppar över valfritt steg {step_key}")
            return True
        return False
    
    # Kör steg
    t0 = time.time()
    try:
        cmd = [sys.executable, str(script_path)]
        log.info(f"   Kör: {' '.join(cmd)}")
        
        # Skicka steg-info som miljövariabler
        env = os.environ.copy()
        env["STEP_NUMBER"] = str(step_key)
        env["STEP_NAME"] = str(step["name"]).replace(" ", "_").lower()
        
        result = subprocess.run(cmd, cwd=SRC_DIR.parent, env=env, check=True)
        elapsed = time.time() - t0
        log.info(f"✓ STEG {step_key} KLART ({elapsed:.1f}s)")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ STEG {step_key} MISSLYCKADES (exit code {e.returncode})")
        return False
    except Exception as e:
        log.error(f"❌ STEG {step_key} MISSLYCKADES: {e}")
        return False


def parse_arguments():
    """Parsa kommanderad-argument."""
    parser = argparse.ArgumentParser(
        description="NMD2 Pipeline Master Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exempel:
  python3 run_all_steps.py              # Kör alla steg
  python3 run_all_steps.py --step 5 7  # Kör endast steg 5-7
  python3 run_all_steps.py --list      # Lista alla steg
        """
    )
    
    parser.add_argument(
        "--step",
        type=int,
        nargs=2,
        metavar=("START", "END"),
        help="Kör endast steg START till END (inklusive)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista alla tillgängliga steg och avsluta"
    )
    
    return parser.parse_args()


def list_steps():
    """Visa alla tillgängliga steg."""
    print("\n📋 Tillgängliga steg:\n")
    for step_key in sorted(STEPS.keys(), key=lambda x: (isinstance(x, str), x)):
        step = STEPS[step_key]
        optional_str = " [VALFRITT]" if step.get("optional") else ""
        print(f"  Steg {step_key}{optional_str}: {step['name']}")
        print(f"         {step['description']}")
    print()


def main():
    """Kör orchestrator."""
    args = parse_arguments()
    
    if args.list:
        list_steps()
        return 0
    
    log.info("")
    log.info("╔" + "═" * 76 + "╗")
    log.info("║ NMD2 PIPELINE — MASTER ORCHESTRATOR")
    log.info("║ Alla steg i en körning")
    log.info("╚" + "═" * 76 + "╝")
    log.info(f"Utmatning: {OUT_BASE}\n")
    
    # Kontrollera förutsättningar
    if not check_requirements():
        log.error("Förutsättningar ej uppfyllda")
        return 1
    
    # Bestäm vilka steg som ska köras
    if args.step:
        start_step, end_step = args.step
        step_keys = [k for k in sorted(STEPS.keys(), key=lambda x: (isinstance(x, str), x))
                     if isinstance(k, int) and start_step <= k <= end_step]
    else:
        step_keys = [k for k in sorted(STEPS.keys(), key=lambda x: (isinstance(x, str), x))]
    
    log.info(f"🔄 Kör: {', '.join(str(k) for k in step_keys)}\n")
    
    # Kör steg
    t0_total = time.time()
    results = {}
    
    for step_key in step_keys:
        results[step_key] = run_step(step_key)
        if not results[step_key]:
            log.error(f"\n❌ Steg {step_key} misslyckades. Avbryter.")
            break
    
    elapsed_total = time.time() - t0_total
    
    # Sammanfattning
    log.info("")
    log.info("=" * 78)
    log.info("📊 RESULTAT")
    log.info("=" * 78)
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for step_key in sorted(results.keys(), key=lambda x: (isinstance(x, str), x)):
        status = "✓ OK" if results[step_key] else "❌ MISSLYCKAD"
        log.info(f"  Steg {step_key}: {status}")
    
    log.info("")
    if success_count == total_count:
        log.info(f"✅ ALLA STEG KLARA ({elapsed_total:.1f}s totalt)\n")
        return 0
    else:
        log.error(f"❌ {total_count - success_count} steg misslyckades\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
