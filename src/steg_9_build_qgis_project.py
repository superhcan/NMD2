#!/usr/bin/env python3
"""
steg_9_build_qgis_project.py — Steg 9: Bygg QGIS-projekt från alla steg.

Läser generaliserad data från alla tidigare steg (1-8) och bygger ett komplett
QGIS-projekt med alla lager organiserade i grupper.

Kör: python3 src/steg_9_build_qgis_project.py

Kräver: QGIS installerat (qgis.core)
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Setup offscreen QGIS användning
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

try:
    sys.path.insert(0, '/usr/lib/python3/dist-packages')
    from qgis.core import (
        QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer,
        QgsLayerTreeGroup, QgsLayerTreeLayer, QgsCoordinateReferenceSystem
    )
except ImportError as e:
    print(f"❌ Kan inte importera QGIS: {e}")
    print("   Installera QGIS först: apt install qgis python3-qgis")
    sys.exit(1)

from config import OUT_BASE

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(out_base):
    """Setup steg-märkad loggning för Steg 9."""
    step_num = os.getenv("STEP_NUMBER", "9")
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

QgsApplication.setPrefixPath('/usr', True)
qgs_app = QgsApplication([], False)

def build_qgis_project():
    """Bygg QGIS-projekt med alla steg."""
    
    # Skapa steg8-katalog
    output_dir = OUT_BASE / "steg9_qgis_project"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    project_path = output_dir / "Pipeline.qgs"
    
    log.info("══════════════════════════════════════════════════════════")
    log.info("Steg 9: Bygga QGIS-projekt från alla generaliserade lager")
    log.info("Källmapp : %s", OUT_BASE)
    log.info("Utmapp   : %s", output_dir)
    log.info("══════════════════════════════════════════════════════════")
    
    # Öppna eller skapa projekt
    log.info(f"\nÖppnar projekt: {project_path.name}")
    project = QgsProject()
    
    if project_path.exists():
        project.read(str(project_path))
        log.info(f"  ✓ Befintligt projekt läst")
    else:
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:3006"))
        log.info(f"  ✓ Nytt projekt skapat (EPSG:3006)")
    
    # Rensa gamla grupper
    root = project.layerTreeRoot()
    root.setName("Pipeline")
    root.setExpanded(False)  # Minimera rot-gruppen
    
    for child in list(root.children()):
        root.removeChildNode(child)
    project.removeAllMapLayers()
    
    log.info("✓ Gamla lager rensade\n")
    
    # Definiera steg och deras katalog (med steg-prefix)
    # Uppdaterad för ny numrering: steg 1-9 (tidigare 1-8)
    steps = [
        (9, "Steg 9 - QGIS-projekt", None),  # Denna steg - ingen egen katalog
        (8, "Steg 8 - Förenklad (Mapshaper)", OUT_BASE / "steg8_simplified"),
        (7, "Steg 7 - Vektoriserad", OUT_BASE / "steg7_vectorized"),
        (6, "Steg 6 - Generaliserad", None),  # Kontrolleras dynamiskt nedan
        (5, "Steg 5 - Fylld öar", OUT_BASE / "steg5_islands_filled"),
        (4, "Steg 4 - Fyllda sjöar", OUT_BASE / "steg4_filled"),
        (3, "Steg 3 - Landskapsbild", OUT_BASE / "steg3_landscape"),
        (2, "Steg 2 - Skyddade klasser", OUT_BASE / "steg2_protected"),
        (1, "Steg 1 - Tiles", OUT_BASE / "steg1_tiles"),
    ]
    
    log.info("Lägger till steg i projekt...\n")
    
    total_layers = 0
    for step_num, step_name, step_dir in steps:
        
        # Hoppa över denna steg (steg 9)
        if step_num == 9:
            continue
        
        # Steg 6: kontrollera dynamiskt att minst en metodkatalog finns
        if step_num == 6:
            all_methods = ["conn4", "conn8", "modal", "semantic"]
            existing_method_dirs = [OUT_BASE / f"steg6_generalized_{m}" for m in all_methods if (OUT_BASE / f"steg6_generalized_{m}").exists()]
            if not existing_method_dirs:
                log.warning(f"⚠️  {step_name:40s} – inga metodkataloger hittades")
                continue
        elif not step_dir.exists():
            log.warning(f"⚠️  {step_name:40s} – katalog saknas")
            continue
        
        # Skapa gruppe (minimerad)
        group = QgsLayerTreeGroup(step_name)
        group.setExpanded(False)
        root.addChildNode(group)
        
        # Speciell hantering för Steg 6 – skapa sub_groups för varje metod + setting
        if step_num == 6:
            methods = ["conn4", "conn8", "modal", "semantic"]
            
            for method in methods:
                method_dir = OUT_BASE / f"steg6_generalized_{method}"
                if not method_dir.exists():
                    log.debug(f"  Metodkatalog saknas: {method_dir.name}")
                    continue
                
                # Skapa sub_group för metoden
                method_group = QgsLayerTreeGroup(f"Generaliserad ({method.upper()})")
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
                    elif method == "modal":
                        # Exempel: ...modal_k03.tif → "k03"
                        if "_k" in layer_name:
                            setting = layer_name.split("_k")[-1][:2]  # "03", "05", etc
                            setting_label = f"Klusterradie k={setting}"
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
                    if "MMU" in label:
                        # Extrahera MMU-värde och sortera fallande (100 överst, 002 underst)
                        mmu_val = int(label.split()[-1].replace("px", ""))
                        return (0, -mmu_val)  # 0 = MMU-typ, negativ för fallande
                    elif "Klusterradie" in label:
                        # Extrahera kernel-värde och sortera fallande (k=15 överst, k=03 underst)
                        k_val = int(label.split("k=")[-1])
                        return (1, -k_val)   # 1 = Kernel-typ, negativ för fallande
                    return (2, label)
                
                for setting_label in sorted(settings_dict.keys(), key=sort_settings):
                    # Skapa sub_group för setting
                    setting_group = QgsLayerTreeGroup(setting_label)
                    setting_group.setExpanded(False)
                    method_group.addChildNode(setting_group)
                    
                    for layer_file in settings_dict[setting_label]:
                        layer_name = layer_file.stem
                        try:
                            layer = QgsRasterLayer(str(layer_file), layer_name, "gdal")
                            if not layer.isValid():
                                log.debug(f"  ✗ {layer_name:45s} (ej giltig)")
                                continue
                            
                            project.addMapLayer(layer, addToLegend=False)
                            tree_layer = QgsLayerTreeLayer(layer)
                            tree_layer.setExpanded(False)
                            setting_group.addChildNode(tree_layer)
                            
                            log.info(f"  ✓ {layer_name:45s}")
                            total_layers += 1
                            
                        except Exception as e:
                            log.warning(f"  ✗ {layer_name:45s} ({e})")
                            continue
                    
                    log.info(f"  {setting_label:45s} ({len(settings_dict[setting_label])} lager)")
                
                log.info(f"  {step_name:45s} {method.upper():6s} ({len(layer_files)} lager totalt)\n")
        
        # Speciell hantering för Steg 7 – metod → MMU/kernel → lager
        elif step_num == 7:
            layer_files = sorted(step_dir.glob("*.gpkg"))
            if not layer_files:
                log.warning(f"⚠️  {step_name:40s} – inga filer hittade")
                continue

            known_methods = ["conn4", "conn8", "modal", "semantic"]

            def _parse_steg7(stem):
                """generalized_conn4_mmu008 → (method, setting_label)"""
                s = stem.replace("generalized_", "", 1)
                for m in known_methods:
                    if s.startswith(m + "_"):
                        rest = s[len(m) + 1:]
                        if rest.startswith("mmu"):
                            return m, f"MMU {rest[3:]}px"
                        elif rest.startswith("k"):
                            return m, f"Klusterradie k={rest[1:]}"
                return None, None

            # Bygg metod → {setting_label: [filer]}
            methods_dict = {}
            for lf in layer_files:
                method, setting_label = _parse_steg7(lf.stem)
                if method is None:
                    continue
                methods_dict.setdefault(method, {}).setdefault(setting_label, []).append(lf)

            for method in [m for m in known_methods if m in methods_dict]:
                method_group = QgsLayerTreeGroup(f"Vektoriserad ({method.upper()})")
                method_group.setExpanded(False)
                group.addChildNode(method_group)

                settings = methods_dict[method]
                def _sort_setting(lbl):
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
                                log.debug(f"  ✗ {lf.stem:45s} (ej giltig)")
                                continue
                            project.addMapLayer(layer, addToLegend=False)
                            tree_layer = QgsLayerTreeLayer(layer)
                            tree_layer.setExpanded(False)
                            setting_group.addChildNode(tree_layer)
                            log.info(f"  ✓ {lf.stem:45s}")
                            total_layers += 1
                        except Exception as e:
                            log.warning(f"  ✗ {lf.stem:45s} ({e})")

                log.info(f"  {method.upper():45s} ({sum(len(v) for v in settings.values())} lager)\n")

        # Speciell hantering för Steg 8 – metod → MMU/kernel → tolerance → lager
        elif step_num == 8:
            layer_files = sorted(step_dir.glob("*.gpkg"))
            if not layer_files:
                log.warning(f"⚠️  {step_name:40s} – inga filer hittade")
                continue

            known_methods = ["conn4", "conn8", "modal", "semantic"]

            def _parse_steg8(stem):
                """conn4_mmu008_simplified_p25 → (method, setting_label, tolerance)"""
                parts = stem.split("_simplified_")
                if len(parts) != 2:
                    return None, None, None
                variant, tolerance = parts[0], parts[1]
                for m in known_methods:
                    if variant.startswith(m + "_"):
                        rest = variant[len(m) + 1:]
                        if rest.startswith("mmu"):
                            return m, f"MMU {rest[3:]}px", tolerance
                        elif rest.startswith("k"):
                            return m, f"Klusterradie k={rest[1:]}", tolerance
                return None, None, None

            # Bygg metod → setting_label → tolerance → [filer]
            methods_dict = {}
            for lf in layer_files:
                method, setting_label, tolerance = _parse_steg8(lf.stem)
                if method is None:
                    continue
                methods_dict \
                    .setdefault(method, {}) \
                    .setdefault(setting_label, {}) \
                    .setdefault(tolerance, []) \
                    .append(lf)

            for method in [m for m in known_methods if m in methods_dict]:
                method_group = QgsLayerTreeGroup(f"Förenklad ({method.upper()})")
                method_group.setExpanded(False)
                group.addChildNode(method_group)

                settings = methods_dict[method]
                def _sort_setting8(lbl):
                    if "MMU" in lbl:
                        return (0, -int(lbl.split()[1].replace("px", "")))
                    k_val = int(lbl.split("k=")[-1])
                    return (1, -k_val)

                tolerance_order = ["p90", "p75", "p50", "p25", "p15"]

                for setting_label in sorted(settings.keys(), key=_sort_setting8):
                    setting_group = QgsLayerTreeGroup(setting_label)
                    setting_group.setExpanded(False)
                    method_group.addChildNode(setting_group)

                    tols = settings[setting_label]
                    for tolerance in [t for t in tolerance_order if t in tols]:
                        tol_group = QgsLayerTreeGroup(tolerance)
                        tol_group.setExpanded(False)
                        setting_group.addChildNode(tol_group)
                        for lf in tols[tolerance]:
                            try:
                                layer = QgsVectorLayer(str(lf), lf.stem, "ogr")
                                if not layer.isValid():
                                    log.debug(f"  ✗ {lf.stem:45s} (ej giltig)")
                                    continue
                                project.addMapLayer(layer, addToLegend=False)
                                tree_layer = QgsLayerTreeLayer(layer)
                                tree_layer.setExpanded(False)
                                tol_group.addChildNode(tree_layer)
                                log.info(f"  ✓ {lf.stem:45s}")
                                total_layers += 1
                            except Exception as e:
                                log.warning(f"  ✗ {lf.stem:45s} ({e})")

                log.info(f"  {method.upper():45s} ({sum(len(v) for vv in settings.values() for v in vv.values())} lager)\n")
        
        else:
            # Standard-hantering för andra steg
            # Bestäm filtyp
            if step_num <= 6:
                # Raster-filer
                layer_files = sorted(step_dir.glob("*.tif"))
            else:
                # Vektor-filer
                layer_files = (sorted(step_dir.glob("*.gpkg")) +
                              sorted(step_dir.glob("*.shp")))
            
            if not layer_files:
                log.warning(f"⚠️  {step_name:40s} – inga filer hittade")
                continue
            
            # Lägg till lager (max 16 per grupp för prestanda)
            layers_added = 0
            for layer_file in layer_files[:16]:
                layer_name = layer_file.stem
                
                try:
                    if layer_file.suffix == ".tif":
                        # Raster-lager
                        layer = QgsRasterLayer(str(layer_file), layer_name, "gdal")
                        if not layer.isValid():
                            log.warning(f"  ✗ {layer_name:45s} (ej giltig)")
                            continue
                    else:
                        # Vektor-lager
                        layer = QgsVectorLayer(str(layer_file), layer_name, "ogr")
                        if not layer.isValid():
                            log.warning(f"  ✗ {layer_name:45s} (ej giltig)")
                            continue
                    
                    # Lägg till i projekt
                    project.addMapLayer(layer, addToLegend=False)
                    tree_layer = QgsLayerTreeLayer(layer)
                    tree_layer.setExpanded(True)  # Expandera lagret i träd
                    group.addChildNode(tree_layer)
                    
                    log.info(f"  ✓ {layer_name:45s}")
                    layers_added += 1
                    total_layers += 1
                    
                except Exception as e:
                    log.warning(f"  ✗ {layer_name:45s} ({e})")
                    continue
            
            log.info(f"  {step_name:45s} → {layers_added} lager\n")
    
    # Spara projekt
    log.info(f"Sparar projekt...")
    project.write(str(project_path))
    log.info(f"  ✓ Sparat: {project_path.name}")
    
    # Minimera legend i XML
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(str(project_path))
        xml_root = tree.getroot()
        legend = xml_root.find("legend")
        if legend is not None:
            legend.set("openPanel", "false")
        tree.write(str(project_path), encoding='utf-8', xml_declaration=True)
        log.info(f"  ✓ Legend minimerad")
    except Exception as e:
        log.warning(f"  ⚠️  Kunde inte minimera legend: {e}")
    
    size_kb = project_path.stat().st_size / 1024
    
    log.info("")
    log.info("══════════════════════════════════════════════════════════")
    log.info(f"Steg 9 KLAR")
    log.info(f"Projekt: {project_path.name} ({size_kb:.1f} KB)")
    log.info(f"Totalt lager: {total_layers}")
    log.info("══════════════════════════════════════════════════════════")
    
    return True


if __name__ == "__main__":
    try:
        success = build_qgis_project()
        sys.exit(0 if success else 1)
    except Exception as e:
        log.error(f"❌ Fel: {e}", exc_info=True)
        sys.exit(1)
    finally:
        qgs_app.exitQgis()
