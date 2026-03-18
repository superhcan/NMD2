#!/usr/bin/env python3
"""
run_all_steps.py — Master orchestrator för NMD2 pipeline.

Kör alla steg i rätt ordning:
  Steg 0: Verifikation - tileluppdelning utan omklassificering (steg_0_verify_tiles.py)
  Steg 1: Tileluppdelning med omklassificering (steg_1_split_tiles.py)
  Steg 2: Extract classes (steg_2_extracted.py)
  Steg 3: Lös upp klasser i omgivande mark (steg_3_dissolve.py)
  Steg 4: Ta bort små sjöar < 0,5 ha (steg_4_fill_islands.py)
  Steg 5: Fylla små öar omringade av vatten (steg_5_filter_lakes.py)
  Steg 6: Generalisering (steg_6_generalize.py)
  Steg 7: Vektorisering (steg_7_vectorize.py)
  Steg 8: Mapshaper-förenkling (steg_8_simplify.py)
  Steg 9: Overlay buildings (steg_9_overlay_buildings.py)
  Steg 99: Bygga QGIS-projekt (steg_99_build_qgis_project.py)

Användning:
  python3 run_all_steps.py              # Kör alla steg
  python3 run_all_steps.py --step 6 9  # Kör endast steg 6-9

Kräver:
  - QGIS (för steg 9)
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

# Import pipeline configuration
sys.path.insert(0, str(Path(__file__).parent / "src"))
from config import ENABLE_STEPS, OUT_BASE, GENERALIZATION_METHODS, PARENT_TILES

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

# ══════════════════════════════════════════════════════════════════════════════
# STEG-DEFINITIONER
# ══════════════════════════════════════════════════════════════════════════════

STEPS = {
    0: {
        "name": "Verifikation - Tileluppdelning (original)",
        "script": "steg_0_verify_tiles.py",
        "description": "Delar original-raster i 1024×1024 px tiles utan omklassificering (för verifikation)"
    },
    1: {
        "name": "Tileluppdelning med omklassificering",
        "script": "steg_1_split_tiles.py",
        "description": "Applicerar CLASS_REMAP på tiles från steg 0",
        "requires_dir": "steg0_verify_tiles"
    },
    2: {
        "name": "Extract classes",
        "script": "steg_2_extracted.py",
        "description": "Extracts EXTRACT_CLASSES to separate layer for later vectorization",
        "requires_dir": "steg1_tiles"
    },
    3: {
        "name": "Lös upp klasser i omgivande mark",
        "script": "steg_3_dissolve.py",
        "description": "Ersätter DISSOLVE_CLASSES med omkringliggande mark för generalisering",
        "requires_dir": "steg1_tiles"
    },
    4: {
        "name": "Ta bort små områden",
        "script": "steg_4_fill_islands.py",
        "description": "Tar bort små sjöar < 0,5 ha (< 50 px) och fyller med omkringliggande",
        "requires_dir": "steg3_dissolved" if ENABLE_STEPS.get(3, True) else "steg1_tiles"
    },
    5: {
        "name": "Fylla små öar",
        "script": "steg_5_filter_lakes.py",
        "description": "Fyller små landöar < 0,5 ha omringade av vatten",
        "requires_dir": "steg4_filled" if ENABLE_STEPS.get(4, True) else "steg3_dissolved"
    },
    6: {
        "name": "Generalisering",
        "script": "steg_6_generalize.py",
        "description": "Generaliserar landskapsbild med sieve, modal, semantic och halo-teknik",
        "requires_dir": None  # Kan läsa från steg4_filled eller steg5_islands_filled
    },
    7: {
        "name": "Vektorisering",
        "script": "steg_7_vectorize.py",
        "description": "Konverterar generaliserade raster till GeoPackage-vektorer",
        "requires_dir": f"steg6_generalized_{next(iter(GENERALIZATION_METHODS))}"
    },
    8: {
        "name": "Mapshaper-förenkling",
        "script": "steg_8_simplify.py",
        "description": "Förenklar vektorer med topologi-bevarad Mapshaper",
        "requires_dir": "steg7_vectorized"
    },
    9: {
        "name": "Overlay buildings",
        "script": "steg_9_overlay_buildings.py",
        "description": "Vektoriserar byggnader från steg 2 och lägger till i steg 8-lager",
        "requires_dir": "steg8_simplified"
    },
    99: {
        "name": "Bygga QGIS-projekt",
        "script": "steg_99_build_qgis_project.py",
        "description": "Bygger QGIS-projekt med alla steg organiserade i grupper",
        "requires_dir": "steg8_simplified"
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
    if req_dir is None:
        return True  # Steg hanterar input-katalog själv (t.ex. steg 5)
    
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
        return False
    
    # Kör steg
    t0 = time.time()
    try:
        cmd = [sys.executable, str(script_path)]
        log.info(f"   Kör: {' '.join(cmd)}")
        
        # Skicka steg-info som miljövariabler
        env = os.environ.copy()
        env["STEP_NUMBER"] = str(step_key)
        # Använd script-namn istället för den långa svenska beskrivningen
        # Extrahera namn efter "steg_X_" för att undvika att få nummer två gånger
        step_name_short = script.replace("steg_", "").replace(".py", "").lower()
        # Ta bort ledande nummer_steg
        parts = step_name_short.split("_", 1)
        if len(parts) > 1:
            step_name_short = parts[1]
        env["STEP_NAME"] = step_name_short
        
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
        print(f"  Steg {step_key}: {step['name']}")
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
        step_keys = [k for k in sorted(STEPS.keys())
                     if start_step <= k <= end_step]
    else:
        step_keys = sorted(STEPS.keys())
    
    # Filtrera enligt ENABLE_STEPS i config
    enabled_steps = [k for k in step_keys if ENABLE_STEPS.get(k, True)]
    disabled_steps = [k for k in step_keys if not ENABLE_STEPS.get(k, True)]
    
    if disabled_steps:
        log.info(f"⏭️  Hoppar över (inaktiverade i config): {', '.join(str(k) for k in disabled_steps)}\n")
    
    log.info(f"🔄 Kör: {', '.join(str(k) for k in enabled_steps)}\n")
    
    # Kör steg
    t0_total = time.time()
    results = {}

    for step_key in enabled_steps:
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
