"""
steg_99_build_qgis_project.py — Steg 99: Bygg QGIS-projekt från alla steg.

Läser generaliserad data från alla tidigare steg (1-8) och bygger ett komplett
QGIS-projekt med alla lager organiserade i grupper.

Kör: python3 src/steg_99_build_qgis_project.py

Kräver: QGIS installerat (qgis.core)
"""

import sys
import os
import time
import logging
from pathlib import Path
from datetime import datetime

# Setup offscreen QGIS användning
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

try:
    sys.path.insert(0, '/usr/lib/python3/dist-packages')
    from qgis.core import (
        QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer,
        QgsLayerTreeGroup, QgsLayerTreeLayer, QgsCoordinateReferenceSystem,
        QgsFillSymbol
    )
    from qgis.PyQt.QtCore import Qt
except ImportError as e:
    print(f"❌ Kan inte importera QGIS: {e}")
    print("   Installera QGIS först: apt install qgis python3-qgis")
    sys.exit(1)

from config import OUT_BASE, SRC, ENABLE_STEPS, SIMPLIFICATION_TOLERANCES, QGIS_INCLUDE_STEPS


def _apply_no_fill(layer):
    """Sätter fyllnadsstil till Ingen fyllning för ett vektorlager.

    Används på alla vektorlager (steg 7-9) så att polygoner visas som enbart
    konturer i QGIS.
    """
    renderer = layer.renderer()
    if renderer is None:
        return
    symbol = renderer.symbol()
    if symbol is None:
        return
    for i in range(symbol.symbolLayerCount()):
        sl = symbol.symbolLayer(i)
        if hasattr(sl, 'setBrushStyle'):
            sl.setBrushStyle(Qt.NoBrush)
    layer.triggerRepaint()


def _apply_qml(layer, tif_files: list):
    """Applicerar QML-stil på ett rasterlager.

    Letar efter en .qml-fil med samma stam som den första tile-filen i tif_files.
    Om ingen hittas görs ingenting (lagret behåller QGIS-standardstil).
    """
    for tif in tif_files:
        qml = tif.with_suffix(".qml")
        if qml.exists():
            layer.loadNamedStyle(str(qml))
            layer.triggerRepaint()
            return


def _ensure_mosaic_vrt(tif_files: list, vrt_path: Path) -> bool:
    """Skapar en VRT-mosaik av tif_files om den inte redan finns.

    Returnerar True om VRT:n finns eller skapades, False vid fel.
    """
    import subprocess
    if vrt_path.exists():
        return True
    if not tif_files:
        return False
    file_list = vrt_path.with_suffix(".filelist.txt")
    file_list.write_text("\n".join(str(f) for f in tif_files))
    r = subprocess.run(
        ["gdalbuildvrt", "-input_file_list", str(file_list), str(vrt_path)],
        capture_output=True, text=True,
    )
    file_list.unlink(missing_ok=True)
    return r.returncode == 0 and vrt_path.exists()

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(out_base):
    """Skapar en logger med tre handlers: debug-fil, summary-fil och console.

    Debug-filen tar emot alla nivåer (DEBUG+); summary-fil och console tar
    bara INFO+. Loggernamnet är 'pipeline.build_qgis'.
    Loggfilnamnen inkluderar steg-info (STEP_NUMBER/STEP_NAME) från miljövariabler
    om de finns, annars default-värden '99' och 'bygga_qgis_projekt'.
    Returnerar (log, log) — samma objekt två gånger för baklängeskompatibilitet
    med kod som använder separata 'log' och 'dbg'-variabler.
    """
    step_num = os.getenv("STEP_NUMBER", "99")
    step_name = os.getenv("STEP_NAME", "bygga_qgis_projekt").lower()
    
    # Logg-kataloger
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    # Timestamp för filnamn
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_suffix = f"steg_{step_num}_{step_name}_{ts}"
    
    # Debug-logg (DEBUG-nivå)
    debug_log = log_dir / f"debug_{step_suffix}.log"
    debug_handler = logging.FileHandler(str(debug_log))
    debug_handler.setLevel(logging.DEBUG)
    debug_formatter = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    debug_handler.setFormatter(debug_formatter)
    
    # Summary-logg (INFO-nivå + console)
    summary_log = summary_dir / f"summary_{step_suffix}.log"
    summary_handler = logging.FileHandler(str(summary_log))
    summary_handler.setLevel(logging.INFO)
    summary_formatter = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    summary_handler.setFormatter(summary_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(summary_formatter)
    
    # Main logger for both debug and summary - using same name as the logger that code writes to
    log_obj = logging.getLogger("pipeline.build_qgis")
    log_obj.setLevel(logging.DEBUG)
    log_obj.propagate = False
    
    # Clear handlers to avoid duplicates
    log_obj.handlers.clear()
    
    # Add all handlers
    log_obj.addHandler(debug_handler)
    log_obj.addHandler(summary_handler)
    log_obj.addHandler(console_handler)
    
    # For compatibility, return same logger twice (some code uses dbg_logger)
    return log_obj, log_obj

log, dbg = setup_logging(OUT_BASE)

# ══════════════════════════════════════════════════════════════════════════════
# QGIS INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════

# QgsApplication måste initieras före alla andra QGIS-anrop.
# setPrefixPath('/usr') pekar på QGIS-installationen (apt-paket på Debian/Ubuntu).
# QgsApplication([], False) = headless-läge utan GUI.
QgsApplication.setPrefixPath('/usr', True)
qgs_app = QgsApplication([], False)

def build_qgis_project():
    """Bygger ett QGIS-projekt (.qgs) med alla pipeline-lager organiserade i grupper.

    Läser utdata från steg 0-9 (om de finns) och lägger till dem som lager i ett
    QgsProject med följande trädstruktur:

      Steg N (grupp, minimerad)
        └─ Metod (t.ex. CONN4)     [steg 6-9 har metodundergrupper]
             └─ Setting (MMU/kernel)
                  └─ Lagernamn

    Steg med specialhantering:
      Steg 6 : Rastergrupper per metod (conn4/conn8/majority/semantic) x MMU/kernel
      Steg 7 : Vektorgrupperper metod x MMU/kernel
      Steg 8 : Vektorgrupper per metod x setting x tolerance (Mapshaper: p25 etc;
               GRASS: dp10, chaiken_t20 etc)
      Steg 9 : Som steg 8 men medbyggnader överlagda
      Övriga : Alla .tif/.gpkg/.shp i katalogen listas platt under steggruppen

    XML-post-processing:
      - Legend-panelen minimeras (openPanel='false')
      - Initial vy sätts till hela källrasterns utbredning via rasterio

    Returnerar True vid framgång.
    """
    _t0 = time.time()
    
    # Skapa steg8-katalog
    output_dir = OUT_BASE / "steg_99_build_qgis_project"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    project_path = output_dir / "Pipeline.qgs"
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 99: Bygga QGIS-projekt från alla generaliserade lager")
    log.info("Källmapp : %s", OUT_BASE)
    log.info("Utmapp   : %s", output_dir)
    log.info("══════════════════════════════════════════════════════════")
    
    # Öppna eller skapa projekt
    log.info(f"\nÖppnar projekt: {project_path.name}")
    project = QgsProject()
    
    if project_path.exists():
        project.read(str(project_path))
        log.info(f"Befintligt projekt läst")
    else:
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:3006"))
        log.info(f"Nytt projekt skapat (EPSG:3006)")
    
    # Rensa gamla grupper
    root = project.layerTreeRoot()
    root.setName("Pipeline")
    root.setExpanded(False)  # Minimera rot-gruppen
    
    for child in list(root.children()):
        root.removeChildNode(child)
    project.removeAllMapLayers()
    
    log.info("Gamla lager rensade\n")
    
    # Definierar alla pipeline-steg med numrering, visningsnamn och katalog.
    # Stegen listas i omvänd ordning (högst steg först) så att mer färdiga lager
    # hamnar överst i QGIS-legendän.
    # step_dir=None för steg 99 (detta steg producerar inga datalager).
    steps = [
        (99, "Step 99 - QGIS project", None),
        (13, "Step 13 - Clipped to raster extent", OUT_BASE / "steg_13_clip_to_raster_extent"),
        (12, "Step 12 - Clipped to footprint", OUT_BASE / "steg_12_clip_to_footprint"),
        (11, "Step 11 - Overlaid external", OUT_BASE / "steg_11_overlay_external"),
        (10, "Step 10 - Merged", OUT_BASE / "steg_10_merge"),
        (9, "Step 9 - Overlaid buildings", OUT_BASE / "steg_9_overlay_buildings"),
        (8, "Step 8 - Simplified", OUT_BASE / "steg_8_simplify"),
        (7, "Step 7 - Vectorized", OUT_BASE / "steg_7_vectorize"),
        ("6b", "Step 6b - Expand water", OUT_BASE / "steg_6b_expand_water"),
        (6, "Step 6 - Generalized", OUT_BASE / "steg_6_generalize"),
        (5, "Step 5 - Filtered islands", OUT_BASE / "steg_5_filter_islands"),
        (4, "Step 4 - Filtered lakes", OUT_BASE / "steg_4_filter_lakes"),
        (3, "Step 3 - Dissolved classes", OUT_BASE / "steg_3_dissolve"),
        (2, "Step 2 - Extracted classes", OUT_BASE / "steg_2_extract"),
        (1, "Step 1 - Reclassified tiles", OUT_BASE / "steg_1_reclassify"),
        (0, "Step 0 - Verification tiles (original)", OUT_BASE / "steg_0_verify_tiles"),
    ]
    
    log.info("Lägger till steg i projekt...\n")
    
    total_layers = 0
    for step_num, step_name, step_dir in steps:
        
        # Hoppa över detta steg (steg 99 producerar självt projektet)
        if step_num == 99:
            continue

        # Hoppa över om katalogen inte existerar (steget inte körts ännu)
        if not step_dir.exists():
            log.warning(f"{step_name:40s} - katalog saknas")
            continue

        if not QGIS_INCLUDE_STEPS.get(step_num, True):
            log.info(f"{step_name:40s} - hoppad (QGIS_INCLUDE_STEPS=False)")
            continue
        
        # Skapa gruppe (minimerad)
        group = QgsLayerTreeGroup(step_name)
        group.setExpanded(False)
        root.addChildNode(group)
        
        # Speciell hantering för Steg 6 - skapa sub_groups för varje metod + setting
        if step_num == 6:
            methods = ["conn4", "conn8", "majority", "semantic"]
            
            for method in methods:
                method_dir = step_dir / method
                if not method_dir.exists():
                    log.debug(f"  Metodkatalog saknas: {method_dir.name}")
                    continue
                
                # Skapa sub_group för metoden
                method_group = QgsLayerTreeGroup(f"Generalized ({method.upper()})")
                method_group.setExpanded(False)
                group.addChildNode(method_group)
                
                # Gruppera filer efter setting (MMU-värde eller kernel-storlek)
                settings_dict = {}
                layer_files = sorted(method_dir.glob("*.tif"))
                
                for layer_file in layer_files:
                    layer_name = layer_file.stem
                    
                    # Extrahera setting från filnamn
                    if method in ["conn4", "conn8", "semantic"]:
                        # Exempel: ...conn4_mmu002.tif → "mmu002"
                        if "mmu" in layer_name:
                            setting = layer_name.split("mmu")[-1][:3]  # "002", "004", etc
                            setting_label = f"MMU {setting}px"
                        else:
                            continue
                    elif method == "majority":
                        # Exempel: ...majority_k03.tif → "k03"
                        if "_k" in layer_name:
                            setting = layer_name.split("_k")[-1][:2]  # "03", "05", etc
                            setting_label = f"Kernel radius k={setting}"
                        else:
                            continue
                    else:
                        continue
                    
                    # Lägg till fil i rätt setting-grupp
                    if setting_label not in settings_dict:
                        settings_dict[setting_label] = []
                    settings_dict[setting_label].append(layer_file)
                
                # Lägg till lager grupperat per setting
                # Sortera så mest generaliserad överst (högsta MMU/kernel underst)
                def sort_settings(label):
                    """Sorteringsnyckel för labels inom en metod.

                    MMU-grupper sorteras fallande på pixelantal (högst generalisering
                    överst); kernel-grupper sorteras fallande på storlek.
                    Okkända labels hamnar sist.
                    """
                    if "MMU" in label:
                        # Extrahera MMU-värde och sortera fallande (100 överst, 002 underst)
                        mmu_val = int(label.split()[-1].replace("px", ""))
                        return (0, -mmu_val)  # 0 = MMU-typ, negativ för fallande
                    elif "Kernel radius" in label:
                        # Extrahera kernel-värde och sortera fallande (k=15 överst, k=03 underst)
                        k_val = int(label.split("k=")[-1])
                        return (1, -k_val)   # 1 = Kernel-typ, negativ för fallande
                    return (2, label)
                
                for setting_label in sorted(settings_dict.keys(), key=sort_settings):
                    tif_files = settings_dict[setting_label]
                    # Skapa VRT-mosaik per setting — ett lager för alla tiles
                    safe_label = setting_label.replace(" ", "_").replace("=", "")
                    vrt_path = method_dir / f"_mosaic_{safe_label}.vrt"
                    if not _ensure_mosaic_vrt(tif_files, vrt_path):
                        log.warning(f"  ✗ {method} {setting_label} — kunde inte skapa VRT")
                        continue
                    layer_name = f"{method}_{safe_label}"
                    try:
                        layer = QgsRasterLayer(str(vrt_path), layer_name, "gdal")
                        if not layer.isValid():
                            log.warning(f"  ✗ {layer_name} (ej giltig)")
                            continue
                        _apply_qml(layer, tif_files)
                        project.addMapLayer(layer, addToLegend=False)
                        tree_layer = QgsLayerTreeLayer(layer)
                        tree_layer.setExpanded(False)
                        method_group.addChildNode(tree_layer)
                        log.info(f"  ✓ {layer_name} ({len(tif_files)} tiles → 1 VRT)")
                        total_layers += 1
                    except Exception as e:
                        log.warning(f"  ✗ {layer_name} ({e})")
                        continue

                log.info(f"  {step_name:45s} {method.upper():6s} ({len(layer_files)} tiles totalt)\n")
        
        # Speciell hantering för Steg 6b — en VRT per metodkatalog
        elif step_num == "6b":
            for method_dir in sorted(step_dir.iterdir()):
                if not method_dir.is_dir():
                    continue
                tif_files = sorted(method_dir.glob("*.tif"))
                if not tif_files:
                    continue
                method_group = QgsLayerTreeGroup(f"Expand water ({method_dir.name})")
                method_group.setExpanded(False)
                group.addChildNode(method_group)

                vrt_path = method_dir / "_mosaic.vrt"
                if not _ensure_mosaic_vrt(tif_files, vrt_path):
                    log.warning(f"  ✗ {method_dir.name} — kunde inte skapa VRT")
                    continue
                layer_name = f"6b_{method_dir.name}"
                try:
                    layer = QgsRasterLayer(str(vrt_path), layer_name, "gdal")
                    if not layer.isValid():
                        log.warning(f"  ✗ {layer_name} (ej giltig)")
                        continue
                    _apply_qml(layer, tif_files)
                    project.addMapLayer(layer, addToLegend=False)
                    tree_layer = QgsLayerTreeLayer(layer)
                    tree_layer.setExpanded(False)
                    method_group.addChildNode(tree_layer)
                    log.info(f"  ✓ {layer_name} ({len(tif_files)} tiles → 1 VRT)")
                    total_layers += 1
                except Exception as e:
                    log.warning(f"  ✗ {layer_name} ({e})")

        # Speciell hantering för Steg 7 - metod → MMU/kernel → lager
        elif step_num == 7:
            layer_files = sorted(step_dir.glob("*.gpkg"))
            if not layer_files:
                log.warning(f"{step_name:40s} - inga filer hittade")
                continue

            known_methods = ["conn4", "conn8", "majority", "semantic"]

            def _parse_steg7(stem):
                """Tolkar filnamnet från steg 7 till (metod, setting_label).

                Exempel:
                  'generalized_conn4_mmu008' → ('conn4', 'MMU 008px')
                  'generalized_majority_k15'    → ('majority', 'Kernel radius k=15')

                Returnerar (None, None) om formatet inte känns igen.
                """
                s = stem.replace("generalized_", "", 1)
                for m in known_methods:
                    if s.startswith(m + "_"):
                        rest = s[len(m) + 1:]
                        if rest.startswith("mmu"):
                            return m, f"MMU {rest[3:]}px"
                        elif rest.startswith("k"):
                            return m, f"Kernel radius k={rest[1:]}"
                return None, None

            # Bygg metod → {setting_label: [filer]}
            methods_dict = {}
            for lf in layer_files:
                method, setting_label = _parse_steg7(lf.stem)
                if method is None:
                    continue
                methods_dict.setdefault(method, {}).setdefault(setting_label, []).append(lf)

            for method in [m for m in known_methods if m in methods_dict]:
                method_group = QgsLayerTreeGroup(f"Vectorized ({method.upper()})")
                method_group.setExpanded(False)
                group.addChildNode(method_group)

                settings = methods_dict[method]
                def _sort_setting(lbl):
                    """Sorteringsnyckel för steg 7-settings: MMU fallande, sedan kernel fallande."""
                    if "MMU" in lbl:
                        return (0, -int(lbl.split()[1].replace("px", "")))
                    k_val = int(lbl.split("k=")[-1])
                    return (1, -k_val)

                for setting_label in sorted(settings.keys(), key=_sort_setting):
                    setting_group = QgsLayerTreeGroup(setting_label)
                    setting_group.setExpanded(False)
                    method_group.addChildNode(setting_group)
                    for lf in settings[setting_label]:
                        try:
                            layer = QgsVectorLayer(str(lf), lf.stem, "ogr")
                            if not layer.isValid():
                                log.debug(f" {lf.stem:45s} (ej giltig)")
                                continue
                            _apply_no_fill(layer)
                            project.addMapLayer(layer, addToLegend=False)
                            tree_layer = QgsLayerTreeLayer(layer)
                            tree_layer.setExpanded(False)
                            setting_group.addChildNode(tree_layer)
                            log.info(f" {lf.stem:45s}")
                            total_layers += 1
                        except Exception as e:
                            log.warning(f" {lf.stem:45s} ({e})")

                log.info(f"  {method.upper():45s} ({sum(len(v) for v in settings.values())} lager)\n")

        # Steg 11 - Overlaid external: ett GPKG per variant direkt i katalogen
        elif step_num == 11:
            layer_files = sorted(step_dir.glob("*.gpkg"))
            if not layer_files:
                log.warning(f"{step_name:40s} - inga filer hittade")
                continue
            for lf in layer_files:
                try:
                    layer = QgsVectorLayer(str(lf), lf.stem, "ogr")
                    if not layer.isValid():
                        log.warning(f"  ✗ {lf.stem} (ej giltig)")
                        continue
                    _apply_no_fill(layer)
                    project.addMapLayer(layer, addToLegend=False)
                    tree_layer = QgsLayerTreeLayer(layer)
                    tree_layer.setExpanded(False)
                    group.addChildNode(tree_layer)
                    log.info(f"  ✓ {lf.stem}  ({lf.stat().st_size/1024**2:.0f} MB)")
                    total_layers += 1
                except Exception as e:
                    log.warning(f"  ✗ {lf.stem} ({e})")

        # Steg 8 - Simplified: variant-subkataloger med strip_NNN.gpkg
        elif step_num == 8:
            variant_dirs = sorted(d for d in step_dir.iterdir() if d.is_dir())
            if not variant_dirs:
                log.warning(f"{step_name:40s} - inga variantkataloger")
                continue
            for vd in variant_dirs:
                strips = sorted(vd.glob("strip_???.gpkg"))
                if not strips:
                    continue
                variant_group = QgsLayerTreeGroup(f"Simplified ({vd.name.upper()})")
                variant_group.setExpanded(False)
                group.addChildNode(variant_group)
                for lf in strips:
                    try:
                        layer = QgsVectorLayer(str(lf), lf.stem, "ogr")
                        if not layer.isValid():
                            log.debug(f"  ✗ {lf.stem} (ej giltig)")
                            continue
                        _apply_no_fill(layer)
                        project.addMapLayer(layer, addToLegend=False)
                        tree_layer = QgsLayerTreeLayer(layer)
                        tree_layer.setExpanded(False)
                        variant_group.addChildNode(tree_layer)
                        log.info(f"  ✓ {vd.name}/{lf.name}")
                        total_layers += 1
                    except Exception as e:
                        log.warning(f"  ✗ {lf.stem} ({e})")
                log.info(f"  {step_name} {vd.name}: {len(strips)} strips\n")

        # Step 9 - With buildings: samma namnformat som steg 8
        # Hanterar Mapshaper (conn4_mmu008_simplified_p25) och GRASS (conn4_morph_disk_r02_dp10)
        elif step_num == 9:
            layer_files = sorted(step_dir.glob("*.gpkg"))
            if not layer_files:
                log.warning(f"{step_name:40s} - inga filer hittade")
                continue

            known_methods = ["conn4", "conn8", "majority", "semantic"]

            import re as _re9

            def _parse_steg9(stem):
                """Tolkar filnamnet från steg 9 till (metod, setting_label, tolerance).

                Identisk logik som _parse_steg8 — steg 9 är samma namnformat som
                steg 8 men med byggnader överlagda.

                Mapshaper-format: 'conn4_mmu008_simplified_p25' → ('conn4','MMU 008px','p25')
                GRASS-format:    'conn4_morph_disk_r02_dp10'   → ('conn4','morph_disk_r02','dp10')

                Returnerar (None, None, None) om formatet inte känns igen.
                """
                # Mapshaper-format
                if "_simplified_" in stem:
                    parts = stem.split("_simplified_")
                    if len(parts) == 2:
                        variant, tolerance = parts[0], parts[1]
                        for m in known_methods:
                            if variant.startswith(m + "_"):
                                rest = variant[len(m) + 1:]
                                if rest.startswith("mmu"):
                                    return m, f"MMU {rest[3:]}px", tolerance
                                elif rest.startswith("k"):
                                    return m, f"Kernel radius k={rest[1:]}", tolerance
                # GRASS-format
                sfx_m = _re9.search(r'_(dp\d+(?:_chaiken_t\d+|_sliding_i\d+(?:_s\d+)?)?|chaiken_t\d+|sliding_i\d+(?:_s\d+)?)$', stem)
                if sfx_m:
                    sfx = sfx_m.group(1)
                    before = stem[:sfx_m.start()]
                    for m in known_methods:
                        if before == m:
                            return m, "(no morph)", sfx
                        if before.startswith(m + "_"):
                            return m, before[len(m) + 1:], sfx
                return None, None, None

            allowed_tolerances = {f"p{t}" for t in SIMPLIFICATION_TOLERANCES}
            methods_dict = {}
            for lf in layer_files:
                method, setting_label, tolerance = _parse_steg9(lf.stem)
                if method is None:
                    log.debug(f"Hoppar {lf.name} - okänt namnformat")
                    continue
                is_grass_sfx = bool(_re9.match(r'dp\d+|chaiken_t\d+', tolerance))
                if not is_grass_sfx and tolerance not in allowed_tolerances:
                    continue
                methods_dict \
                    .setdefault(method, {}) \
                    .setdefault(setting_label, {}) \
                    .setdefault(tolerance, []) \
                    .append(lf)

            for method in [m for m in known_methods if m in methods_dict]:
                method_group = QgsLayerTreeGroup(f"With buildings ({method.upper()})")
                method_group.setExpanded(False)
                group.addChildNode(method_group)

                settings = methods_dict[method]
                def _sort_setting9(lbl):
                    """Sorteringsnyckel för steg 9-labels: identisk med _sort_setting8."""
                    if "MMU" in lbl:
                        return (0, -int(lbl.split()[1].replace("px", "")))
                    if "k=" in lbl:
                        return (1, -int(lbl.split("k=")[-1]))
                    return (2, lbl)

                mapshaper_tol_order = ["p90", "p75", "p50", "p25", "p15"]

                for setting_label in sorted(settings.keys(), key=_sort_setting9):
                    setting_group = QgsLayerTreeGroup(setting_label)
                    setting_group.setExpanded(False)
                    method_group.addChildNode(setting_group)

                    tols = settings[setting_label]
                    # Mapshaper: fast ordning från minst till mest förenklad;
                    # GRASS: övriga nyckel läggs till sorterade sist.
                    ordered = [t for t in mapshaper_tol_order if t in tols] + \
                              sorted(t for t in tols if t not in mapshaper_tol_order)
                    for tolerance in ordered:
                        tol_group = QgsLayerTreeGroup(tolerance)
                        tol_group.setExpanded(False)
                        setting_group.addChildNode(tol_group)
                        for lf in tols[tolerance]:
                            try:
                                layer = QgsVectorLayer(str(lf), lf.stem, "ogr")
                                if not layer.isValid():
                                    log.debug(f" {lf.stem:45s} (ej giltig)")
                                    continue
                                _apply_no_fill(layer)
                                project.addMapLayer(layer, addToLegend=False)
                                tree_layer = QgsLayerTreeLayer(layer)
                                tree_layer.setExpanded(False)
                                tol_group.addChildNode(tree_layer)
                                log.info(f" {lf.stem:45s}")
                                total_layers += 1
                            except Exception as e:
                                log.warning(f" {lf.stem:45s} ({e})")

                log.info(f"  {method.upper():45s} ({sum(len(v) for vv in settings.values() for v in vv.values())} lager)\n")

        # Steg 10 - Merged: ett GPKG per variant direkt i katalogen
        elif step_num == 10:
            layer_files = sorted(step_dir.glob("*.gpkg"))
            if not layer_files:
                log.warning(f"{step_name:40s} - inga filer hittade")
                continue
            for lf in layer_files:
                try:
                    layer = QgsVectorLayer(str(lf), lf.stem, "ogr")
                    if not layer.isValid():
                        log.warning(f"  ✗ {lf.stem} (ej giltig)")
                        continue
                    _apply_no_fill(layer)
                    project.addMapLayer(layer, addToLegend=False)
                    tree_layer = QgsLayerTreeLayer(layer)
                    tree_layer.setExpanded(False)
                    group.addChildNode(tree_layer)
                    log.info(f"  ✓ {lf.stem}  ({lf.stat().st_size/1024**2:.0f} MB)")
                    total_layers += 1
                except Exception as e:
                    log.warning(f"  ✗ {lf.stem} ({e})")

        else:
            # Standard-hantering för steg 0-5: bygg en VRT-mosaik av alla tiles
            # och lägg till den som ett enda lager under steggruppen.
            if step_num <= 5:
                tif_files = sorted(step_dir.glob("*.tif"))
                if not tif_files:
                    log.warning(f"{step_name:40s} - inga TIF-filer hittade")
                    continue
                vrt_path = step_dir / "_mosaic.vrt"
                if not _ensure_mosaic_vrt(tif_files, vrt_path):
                    log.warning(f"{step_name:40s} - kunde inte skapa VRT-mosaik")
                    continue
                layer_name = f"steg_{step_num}_mosaic"
                try:
                    layer = QgsRasterLayer(str(vrt_path), layer_name, "gdal")
                    if not layer.isValid():
                        log.warning(f"  ✗ {layer_name} (ej giltig)")
                        continue
                    _apply_qml(layer, tif_files)
                    project.addMapLayer(layer, addToLegend=False)
                    tree_layer = QgsLayerTreeLayer(layer)
                    tree_layer.setExpanded(True)
                    group.addChildNode(tree_layer)
                    log.info(f"  ✓ {layer_name} ({len(tif_files)} tiles → 1 VRT)")
                    total_layers += 1
                except Exception as e:
                    log.warning(f"  ✗ {layer_name} ({e})")
                    continue
            else:
                # Vektor-filer (steg >6 som inte matchats ovan)
                layer_files = (sorted(step_dir.glob("*.gpkg")) +
                              sorted(step_dir.glob("*.shp")))
                if not layer_files:
                    log.warning(f"{step_name:40s} - inga filer hittade")
                    continue
                layers_added = 0
                for layer_file in layer_files:
                    layer_name = layer_file.stem
                    try:
                        layer = QgsVectorLayer(str(layer_file), layer_name, "ogr")
                        if not layer.isValid():
                            log.warning(f"  ✗ {layer_name:45s} (ej giltig)")
                            continue
                        _apply_no_fill(layer)
                        project.addMapLayer(layer, addToLegend=False)
                        tree_layer = QgsLayerTreeLayer(layer)
                        tree_layer.setExpanded(True)
                        group.addChildNode(tree_layer)
                        log.info(f" {layer_name:45s}")
                        layers_added += 1
                        total_layers += 1
                    except Exception as e:
                        log.warning(f" {layer_name:45s} ({e})")
                        continue
                log.info(f"  {step_name:45s} → {layers_added} lager\n")
    
    # Spara projekt
    log.info(f"Sparar projekt...")
    project.write(str(project_path))
    log.info(f" Sparat: {project_path.name}")
    
    # Minimera legend i XML + sätt initial vy till hela källrasterns utbredning
    import xml.etree.ElementTree as ET
    import rasterio
    try:
        tree = ET.parse(str(project_path))
        xml_root = tree.getroot()

        # Minimera legendpanelen
        legend = xml_root.find("legend")
        if legend is not None:
            legend.set("openPanel", "false")

        # Sätt initial mapcanvas-vy till hela källrasterns utbredning så att
        # QGIS inte zoomar in till det första lagret (övre vänstra tilen) vid öppning.
        with rasterio.open(SRC) as src_raster:
            b = src_raster.bounds   # left, bottom, right, top
        mapcanvas = xml_root.find("mapcanvas[@name='theMapCanvas']")
        if mapcanvas is None:
            mapcanvas = xml_root.find("mapcanvas")
        if mapcanvas is not None:
            ext = mapcanvas.find("extent")
            if ext is None:
                ext = ET.SubElement(mapcanvas, "extent")
            for tag, val in [("xmin", b.left), ("ymin", b.bottom),
                              ("xmax", b.right), ("ymax", b.top)]:
                el = ext.find(tag)
                if el is None:
                    el = ET.SubElement(ext, tag)
                el.text = str(val)
            log.info(f" Initial vy satt till hela källrasterns utbredning "
                     f"({b.left:.0f},{b.bottom:.0f} → {b.right:.0f},{b.top:.0f})")
        else:
            log.warning("Kunde inte hitta mapcanvas i XML — initial vy ej satt")

        tree.write(str(project_path), encoding='utf-8', xml_declaration=True)
        log.info(f" Legend minimerad")
    except Exception as e:
        log.warning(f"Kunde inte modifiera XML: {e}")
    
    size_kb = project_path.stat().st_size / 1024
    
    log.info("")
    log.info("══════════════════════════════════════════════════════════")
    _elapsed = time.time() - _t0
    log.info(f"Steg 99 KLART  {_elapsed / 60:.1f} min ({_elapsed:.0f}s)")
    log.info(f"Projekt: {project_path.name} ({size_kb:.1f} KB)")
    log.info(f"Totalt lager: {total_layers}")
    log.info("══════════════════════════════════════════════════════════")
    
    return True


if __name__ == "__main__":
    try:
        success = build_qgis_project()
        sys.exit(0 if success else 1)
    except Exception as e:
        log.error(f"Fel: {e}", exc_info=True)
        sys.exit(1)
    finally:
        qgs_app.exitQgis()
