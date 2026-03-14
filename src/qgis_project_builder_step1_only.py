#!/usr/bin/env python3
"""
QGIS Project Builder - Step 1 Only
Baserat på Pipeline_s1.qgs struktur - exakt formaterad XML
"""

import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime

import rasterio


class QGISProjectBuilderStep1:
    """Builder för exakt QGIS-projekt matchande Pipeline_s1.qgs"""

    def __init__(self, out_base: Path, project_name: str = "Pipeline"):
        self.out_base = Path(out_base)
        self.project_name = project_name
        self.project_path = self.out_base / f"{project_name}.qgs"
        self.layer_ids = []
        self.extent = None
        self._init_project()

    def _init_project(self):
        """Initialize project matching Pipeline_s1.qgs exactly"""
        self.root = ET.Element("qgis")
        self.root.set("projectname", "")
        self.root.set("saveDateTime", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        self.root.set("version", "3.44.7-Solothurn")
        self.root.set("saveUser", "hcn")
        self.root.set("saveUserFull", "hcn")

        # homePath
        home_path = ET.SubElement(self.root, "homePath")
        home_path.set("path", "")
        
        # title
        title = ET.SubElement(self.root, "title")
        title.text = ""
        
        # transaction
        trans = ET.SubElement(self.root, "transaction")
        trans.set("mode", "Disabled")
        
        # projectFlags
        flags = ET.SubElement(self.root, "projectFlags")
        flags.set("set", "")

        # projectCrs
        self._add_crs()
        
        # verticalCrs
        self._add_vertical_crs()
        
        # elevation-shading-renderer
        esr = ET.SubElement(self.root, "elevation-shading-renderer")
        esr.set("edl-distance-unit", "0")
        esr.set("hillshading-is-multidirectional", "0")
        esr.set("is-active", "0")
        esr.set("edl-is-active", "1")
        esr.set("hillshading-is-active", "0")
        esr.set("combined-method", "0")
        esr.set("edl-strength", "1000")
        esr.set("hillshading-z-factor", "1")
        esr.set("edl-distance", "0.5")
        esr.set("light-altitude", "45")
        esr.set("light-azimuth", "315")

        # layer-tree-group (root)
        self.root_group = ET.SubElement(self.root, "layer-tree-group")
        
        # customproperties for root
        custom_props = ET.SubElement(self.root_group, "customproperties")
        ET.SubElement(custom_props, "Option")
        
        # Add Step 1 group (only one for this version)
        self.step1_group = ET.SubElement(self.root_group, "layer-tree-group")
        self.step1_group.set("name", "Step 1 - Split Tiles")
        self.step1_group.set("groupLayer", "")
        self.step1_group.set("expanded", "0")
        self.step1_group.set("checked", "Qt::Unchecked")
        
        # customproperties for Step 1
        step1_props = ET.SubElement(self.step1_group, "customproperties")
        ET.SubElement(step1_props, "Option")
        
        # Add empty Step 2-7 groups
        for step_num in range(2, 8):
            if step_num == 2:
                name = "Step 2 - Protected Classes"
                expanded = "1"
            elif step_num == 5:
                name = "Step 5 - Generalized"
                expanded = "0"
            else:
                name = f"Step {step_num}"
                expanded = "0"
            
            step_group = ET.SubElement(self.root_group, "layer-tree-group")
            step_group.set("name", name)
            step_group.set("groupLayer", "")
            step_group.set("expanded", expanded)
            step_group.set("checked", "Qt::Checked")
            
            props = ET.SubElement(step_group, "customproperties")
            ET.SubElement(props, "Option")
            
            # Special: Step 5 has Modal Filter subgroup
            if step_num == 5:
                modal_group = ET.SubElement(step_group, "layer-tree-group")
                modal_group.set("name", "Modal Filter")
                modal_group.set("groupLayer", "")
                modal_group.set("expanded", "0")
                modal_group.set("checked", "Qt::Checked")
                
                modal_props = ET.SubElement(modal_group, "customproperties")
                ET.SubElement(modal_props, "Option")
        
        # custom-order (will fill during save)
        self.custom_order_elem = None

    def _add_crs(self):
        """Add projectCrs element"""
        pcrs = ET.SubElement(self.root, "projectCrs")
        srs = ET.SubElement(pcrs, "spatialrefsys")
        srs.set("nativeFormat", "Wkt")
        
        for tag in ["wkt", "proj4"]:
            elem = ET.SubElement(srs, tag)
            elem.text = ""
        
        srsid = ET.SubElement(srs, "srsid")
        srsid.text = "0"
        
        srid = ET.SubElement(srs, "srid")
        srid.text = "0"
        
        authid = ET.SubElement(srs, "authid")
        authid.text = ""
        
        for tag in ["description", "projectionacronym", "ellipsoidacronym"]:
            elem = ET.SubElement(srs, tag)
            elem.text = ""
        
        geo = ET.SubElement(srs, "geographicflag")
        geo.text = "false"

    def _add_vertical_crs(self):
        """Add verticalCrs element"""
        vcrs = ET.SubElement(self.root, "verticalCrs")
        srs = ET.SubElement(vcrs, "spatialrefsys")
        srs.set("nativeFormat", "Wkt")
        
        for tag in ["wkt", "proj4"]:
            elem = ET.SubElement(srs, tag)
            elem.text = ""
        
        srsid = ET.SubElement(srs, "srsid")
        srsid.text = "0"
        
        srid = ET.SubElement(srs, "srid")
        srid.text = "0"
        
        authid = ET.SubElement(srs, "authid")
        authid.text = ""
        
        for tag in ["description", "projectionacronym", "ellipsoidacronym"]:
            elem = ET.SubElement(srs, tag)
            elem.text = ""
        
        geo = ET.SubElement(srs, "geographicflag")
        geo.text = "false"

    def add_raster_layer_to_step1(self, tif_path: Path, layer_name: str, layer_id: str, 
                                   patch_size: str = "-1,-1", expanded: str = "0"):
        """Add raster layer to Step 1"""
        tif_path = Path(tif_path)
        if not tif_path.exists():
            raise FileNotFoundError(f"Raster not found: {tif_path}")
        
        # Read extent
        if not self.extent:
            try:
                with rasterio.open(tif_path) as src:
                    bounds = src.bounds
                    self.extent = (
                        bounds.left, bounds.bottom, bounds.right, bounds.top
                    )
            except Exception as e:
                print(f"⚠️  Could not read extent: {e}")
        
        # Create layer element
        layer = ET.SubElement(self.step1_group, "layer-tree-layer")
        layer.set("name", layer_name)
        layer.set("providerKey", "gdal")
        layer.set("patch_size", patch_size)
        layer.set("expanded", expanded)
        layer.set("legend_exp", "")
        layer.set("legend_split_behavior", "0")
        layer.set("source", f"./tiles/{tif_path.name}")
        layer.set("checked", "Qt::Checked")
        layer.set("id", layer_id)
        
        # customproperties
        props = ET.SubElement(layer, "customproperties")
        ET.SubElement(props, "Option")
        
        self.layer_ids.append(layer_id)

    def save(self) -> Path:
        """Save project as .qgs file"""
        # Add custom-order before save
        custom_order = ET.SubElement(self.root_group, "custom-order")
        custom_order.set("enabled", "0")
        for lid in self.layer_ids:
            item = ET.SubElement(custom_order, "item")
            item.text = lid
        
        # Add snapping settings
        snapping = ET.SubElement(self.root, "snapping-settings")
        snapping.set("scaleDependencyMode", "0")
        snapping.set("maxScale", "0")
        snapping.set("type", "1")
        snapping.set("tolerance", "0")
        snapping.set("minScale", "0")
        snapping.set("mode", "3")
        snapping.set("enabled", "1")
        snapping.set("self-snapping", "0")
        snapping.set("unit", "2")
        snapping.set("intersection-snapping", "0")
        ET.SubElement(snapping, "individual-layer-settings")
        
        # Add empty elements
        ET.SubElement(self.root, "relations")
        ET.SubElement(self.root, "polymorphicRelations")
        
        # Save directly as .qgs (no temp dir needed)
        tree = ET.ElementTree(self.root)
        tree.write(self.project_path, encoding="UTF-8", xml_declaration=False)
        
        # Read and add DOCTYPE
        with open(self.project_path, 'r') as f:
            content = f.read()
        
        with open(self.project_path, 'w') as f:
            f.write('<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n')
            f.write(content)
        
        size_kb = self.project_path.stat().st_size / 1024
        print(f"✅ QGIS project saved: {self.project_path.name} ({size_kb:.1f} KB)")
        return self.project_path

    def cleanup(self):
        """Cleanup (not needed anymore)"""
        pass


def main():
    """Run Step 1 and create project"""
    from pipeline_1024_halo import step1_split, OUT_BASE
    
    print("🚀 Creating QGIS project with Step 1 ONLY")
    
    builder = QGISProjectBuilderStep1(OUT_BASE)
    
    # Run Step 1: Split tiles
    print("📋 Step 1: Split tiles")
    tile_paths = step1_split()
    print(f"   Found {len(tile_paths)} tiles")
    
    # Add ALL tiles to project
    for tile in sorted(tile_paths):
        layer_name = tile.stem
        # Generate consistent layer ID from name
        layer_id = f"{layer_name}_{tile.stem[-8:]}"
        builder.add_raster_layer_to_step1(tile, layer_name, layer_id)
        print(f"   Added: {layer_name}")
    
    # Save project
    builder.save()
    print(f"✅ Project ready: {OUT_BASE / 'Pipeline.qgz'}")
    
    builder.cleanup()


if __name__ == "__main__":
    main()
