#!/usr/bin/env python3
"""
QGIS Project Builder - Copy reference and modify
Baserat på Pipeline_s1.qgs - erstätter bara layers med Step 1 tiles
"""

import shutil
from pathlib import Path
from xml.etree import ElementTree as ET
import uuid

def create_project_from_template(template_path: Path, out_path: Path, tile_paths: list):
    """
    Parse template, replace Step 1 layers, save as new project
    """
    print(f"📋 Laddar template: {template_path.name}")
    
    tree = ET.parse(template_path)
    root = tree.getroot()
    
    # Find layer-tree-group for Step 1
    layer_tree_groups = root.findall(".//layer-tree-group[@name]")
    step1_group = None
    for group in layer_tree_groups:
        if "Split Tiles" in group.get("name", ""):
            step1_group = group
            break
    
    if not step1_group:
        print("❌ Kunde inte hitta 'Step 1 - Split Tiles' grupp")
        return
    
    # Clear existing layers from Step 1
    print(f"🗑️  Tar bort gamla lager från Step 1")
    existing_layers = step1_group.findall("layer-tree-layer")
    for layer in existing_layers:
        step1_group.remove(layer)
    
    # Clear custom-order
    custom_orders = root.findall(".//custom-order")
    for co in custom_orders:
        root.find(".//layer-tree-group").remove(co)
    
    # Add new layers to Step 1
    print(f"➕ Lägger till {len(tile_paths)} nya lager")
    layer_ids = []
    for tile_path in sorted(tile_paths):
        tile_path = Path(tile_path)
        layer_name = tile_path.stem
        layer_id = f"{layer_name}_{str(uuid.uuid4())}"
        
        layer_elem = ET.SubElement(step1_group, "layer-tree-layer")
        layer_elem.set("name", layer_name)
        layer_elem.set("providerKey", "gdal")
        layer_elem.set("patch_size", "-1,-1")
        layer_elem.set("expanded", "0")
        layer_elem.set("legend_exp", "")
        layer_elem.set("legend_split_behavior", "0")
        layer_elem.set("source", f"./tiles/{tile_path.name}")
        layer_elem.set("checked", "Qt::Checked")
        layer_elem.set("id", layer_id)
        
        props = ET.SubElement(layer_elem, "customproperties")
        ET.SubElement(props, "Option")
        
        layer_ids.append(layer_id)
        print(f"   ✓ {layer_name}")
    
    # Rebuild custom-order
    root_group = root.find(".//layer-tree-group")
    custom_order = ET.SubElement(root_group, "custom-order")
    custom_order.set("enabled", "0")
    for lid in layer_ids:
        item = ET.SubElement(custom_order, "item")
        item.text = lid
    
    # Save
    tree.write(out_path, encoding="UTF-8", xml_declaration=False)
    
    # Add DOCTYPE
    with open(out_path, 'r') as f:
        content = f.read()
    
    with open(out_path, 'w') as f:
        f.write('<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n')
        f.write(content)
    
    size_kb = out_path.stat().st_size / 1024
    print(f"✅ Projekt sparad: {out_path.name} ({size_kb:.1f} KB)")
    return out_path


def main():
    from pipeline_1024_halo import step1_split, OUT_BASE
    
    template = OUT_BASE / "Pipeline_s1.qgs"
    output = OUT_BASE / "Pipeline.qgs"
    
    if not template.exists():
        print(f"❌ Referensfilen saknas: {template}")
        return
    
    tile_paths = step1_split()
    print(f"📊 Hittat {len(tile_paths)} tiles")
    
    create_project_from_template(template, output, tile_paths)


if __name__ == "__main__":
    main()
