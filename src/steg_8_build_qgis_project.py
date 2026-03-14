#!/usr/bin/env python3
"""
steg_8_build_qgis_project.py — Steg 8: Bygg QGIS-projekt från alla steg.

Läser generaliserad data från alla tidigare steg (1-7) och bygger ett komplett
QGIS-projekt med alla lager organiserade i grupper.

Kör: python3 src/steg_8_build_qgis_project.py

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
    """Setup steg-märkad loggning för Steg 8."""
    step_num = os.getenv("STEP_NUMBER", "8")
    step_name = os.getenv("STEP_NAME", "bygga_qgis_projekt").lower()
    
    # Logg-kataloger
    log_dir = out_base / "log"
    summary_dir = out_base / "summary"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    # Timestamp för filnamn
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    step_suffix = f"_steg{step_num}_{step_name}_{ts}"
    
    # Debug-logg (DEBUG-nivå)
    debug_log = log_dir / f"pipeline_debug{step_suffix}.log"
    debug_handler = logging.FileHandler(str(debug_log))
    debug_handler.setLevel(logging.DEBUG)
    debug_formatter = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    debug_handler.setFormatter(debug_formatter)
    
    # Summary-logg (INFO-nivå + console)
    summary_log = summary_dir / f"pipeline_summary{step_suffix}.log"
    summary_handler = logging.FileHandler(str(summary_log))
    summary_handler.setLevel(logging.INFO)
    summary_formatter = logging.Formatter("%(asctime)s [%(levelname)-6s] %(message)s", datefmt="%H:%M:%S")
    summary_handler.setFormatter(summary_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(summary_formatter)
    
    # Debug-loggare
    dbg_logger = logging.getLogger("pipeline.build_qgis.debug")
    dbg_logger.setLevel(logging.DEBUG)
    dbg_logger.addHandler(debug_handler)
    dbg_logger.propagate = False
    
    # Summary-loggare
    log_obj = logging.getLogger("pipeline.build_qgis")
    log_obj.setLevel(logging.INFO)
    log_obj.addHandler(summary_handler)
    log_obj.addHandler(console_handler)
    log_obj.propagate = False
    
    return log_obj, dbg_logger

log, dbg = setup_logging(OUT_BASE)

# ══════════════════════════════════════════════════════════════════════════════
# QGIS INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════

QgsApplication.setPrefixPath('/usr', True)
qgs_app = QgsApplication([], False)

def build_qgis_project():
    """Bygg QGIS-projekt med alla steg."""
    
    # Skapa steg8-katalog
    output_dir = OUT_BASE / "steg8_qgis_project"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    project_path = output_dir / "Pipeline.qgs"
    
    log.info("═" * 70)
    log.info("Steg 8: Bygger QGIS-projekt från alla generer lager")
    log.info("═" * 70)
    
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
    
    log.info("✓ Gamla lager rensade\n")
    
    # Definiera steg och deras katalog (med steg-prefix)
    steps = [
        (7, "Steg 7 - Förenklad (Mapshaper)", OUT_BASE / "steg7_simplified"),
        (6, "Steg 6 - Vektoriserad", OUT_BASE / "steg6_vectorized"),
        (5, "Steg 5 - Fyllda områden", OUT_BASE / "steg5_filled"),
        (4, "Steg 4 - Generaliserad", OUT_BASE / "steg4_generalized_modal"),
        (3, "Steg 3 - Landskapsbild", OUT_BASE / "steg3_landscape"),
        (2, "Steg 2 - Skyddade klasser", OUT_BASE / "steg2_protected"),
        (1, "Steg 1 - Tiles", OUT_BASE / "steg1_tiles"),
    ]
    
    log.info("Lägger till steg i projekt...\n")
    
    total_layers = 0
    for step_num, step_name, step_dir in steps:
        
        if not step_dir.exists():
            log.warning(f"⚠️  {step_name:40s} – katalog saknas")
            continue
        
        # Skapa gruppe (minimerad)
        group = QgsLayerTreeGroup(step_name)
        group.setExpanded(False)
        root.addChildNode(group)
        
        # Speciell hantering för Steg 4 – skapa sub_groups för varje metod
        if step_num == 4:
            methods = ["conn4", "conn8", "modal", "semantic"]
            
            for method in methods:
                method_dir = step_dir.parent / f"steg4_generalized_{method}"
                if not method_dir.exists():
                    log.debug(f"  Metodkatalog saknas: {method_dir.name}")
                    continue
                
                # Skapa sub_group för metoden
                subgroup = QgsLayerTreeGroup(f"Generaliserad ({method.upper()})")
                subgroup.setExpanded(False)
                group.addChildNode(subgroup)
                
                # Lägg till raster-filer från denna metod
                layer_files = sorted(method_dir.glob("*.tif"))[:16]  # Max 16 per subgroup
                
                for layer_file in layer_files:
                    layer_name = layer_file.stem
                    try:
                        layer = QgsRasterLayer(str(layer_file), layer_name, "gdal")
                        if not layer.isValid():
                            log.debug(f"  ✗ {layer_name:45s} (ej giltig)")
                            continue
                        
                        project.addMapLayer(layer, addToLegend=False)
                        tree_layer = QgsLayerTreeLayer(layer)
                        tree_layer.setExpanded(False)
                        subgroup.addChildNode(tree_layer)
                        
                        log.info(f"  ✓ {layer_name:45s}")
                        total_layers += 1
                        
                    except Exception as e:
                        log.warning(f"  ✗ {layer_name:45s} ({e})")
                        continue
                
                log.info(f"  {step_name:45s} → {method.upper():6s} {len(layer_files)} lager\n")
        
        else:
            # Standard-hantering för andra steg
            # Bestäm filtyp
            if step_num <= 5:
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
    log.info("═" * 70)
    log.info(f"✅ Steg 8 KLART")
    log.info(f"   Projekt: {project_path.name} ({size_kb:.1f} KB)")
    log.info(f"   Totalt lager: {total_layers}")
    log.info(f"   Ordning: Steg 7 (top) → Steg 1 (bottom)")
    log.info("═" * 70)
    
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
