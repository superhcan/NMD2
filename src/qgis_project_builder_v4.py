#!/usr/bin/env python3
"""
QGIS Project Builder v4 - Dynamisk hierarkisk builder
Bygger QGIS-projekt med steg och metod-undergrupper enligt dokumenterad struktur.
"""

import shutil
import tempfile
import zipfile
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Optional, Dict, List

import rasterio


class QGISProjectBuilder:
    """Dynamisk QGIS-projektbyggare med hierarkisk struktur."""

    def __init__(self, out_base: Path, project_name: str = "Pipeline"):
        self.out_base = Path(out_base)
        self.project_name = project_name
        self.project_path = self.out_base / f"{project_name}.qgz"
        self.temp_dir = tempfile.mkdtemp(prefix="qgis_project_")
        self.temp_dir_path = Path(self.temp_dir)

        # XML-struktur
        self.root = None
        self.maplayers_element = None
        self.layer_tree_group = None
        self.legend_element = None

        # Hierarki-tracking
        self.group_stack = []  # Stack av grupper för nested structure
        self.layer_counter = 0
        self.extent = None
        self.crs_id = "EPSG:3006"  # SWEREF99 TM

        # Initialize project
        self._init_project()

    def _init_project(self) -> None:
        """Initialize empty QGIS project structure."""
        # Root element
        self.root = ET.Element("qgis")
        self.root.set("projectname", self.project_name)
        self.root.set("version", "3.44.7-Solothurn")
        self.root.set("saveUser", "hcn")
        self.root.set("saveUserFull", "hcn")

        # Add basic structure
        ET.SubElement(self.root, "homePath").set("path", "")
        ET.SubElement(self.root, "title").text = ""
        
        # Transaction mode
        ET.SubElement(self.root, "transaction").set("mode", "Disabled")
        
        # Project flags
        ET.SubElement(self.root, "projectFlags").set("set", "")

        # CRS and vertical CRS
        self._add_crs()
        self._add_vertical_crs()
        
        # Elevation shading renderer
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

        # Add layer-tree-group (root group)
        layer_tree = ET.SubElement(self.root, "layer-tree-group")
        layer_tree.set("checked", "Qt::Checked")
        layer_tree.set("expanded", "1")
        layer_tree.set("name", self.project_name)
        
        # Add custom properties to root group
        custom_props = ET.SubElement(layer_tree, "customproperties")
        ET.SubElement(custom_props, "Option")

        self.layer_tree_group = layer_tree
        self.group_stack = [layer_tree]
        self.custom_order = []  # Track layer IDs for custom-order

        # NOTE: No legend, maplayers, or canvas elements - these are not used in modern QGIS

    def _add_crs(self) -> None:
        """Add CRS (EPSG:3006 - SWEREF99 TM)."""
        srs = ET.SubElement(self.root, "projectCrs")
        srs_id = ET.SubElement(srs, "spatialrefsys")
        srs_id.set("nativeFormat", "Wkt")

        wkt = ET.SubElement(srs_id, "wkt")
        wkt.text = ""
        
        proj4 = ET.SubElement(srs_id, "proj4")
        proj4.text = ""
        
        srsid = ET.SubElement(srs_id, "srsid")
        srsid.text = "0"
        
        srid = ET.SubElement(srs_id, "srid")
        srid.text = "0"
        
        authid = ET.SubElement(srs_id, "authid")
        authid.text = ""
        
        description = ET.SubElement(srs_id, "description")
        description.text = ""
        
        projectionacronym = ET.SubElement(srs_id, "projectionacronym")
        projectionacronym.text = ""
        
        ellipsoidacronym = ET.SubElement(srs_id, "ellipsoidacronym")
        ellipsoidacronym.text = ""
        
        geographicflag = ET.SubElement(srs_id, "geographicflag")
        geographicflag.text = "false"

    def _add_vertical_crs(self) -> None:
        """Add vertical CRS."""
        vcrs = ET.SubElement(self.root, "verticalCrs")
        srs_id = ET.SubElement(vcrs, "spatialrefsys")
        srs_id.set("nativeFormat", "Wkt")

        wkt = ET.SubElement(srs_id, "wkt")
        wkt.text = ""
        
        proj4 = ET.SubElement(srs_id, "proj4")
        proj4.text = ""
        
        srsid = ET.SubElement(srs_id, "srsid")
        srsid.text = "0"
        
        srid = ET.SubElement(srs_id, "srid")
        srid.text = "0"
        
        authid = ET.SubElement(srs_id, "authid")
        authid.text = ""
        
        description = ET.SubElement(srs_id, "description")
        description.text = ""
        
        projectionacronym = ET.SubElement(srs_id, "projectionacronym")
        projectionacronym.text = ""
        
        ellipsoidacronym = ET.SubElement(srs_id, "ellipsoidacronym")
        ellipsoidacronym.text = ""
        
        geographicflag = ET.SubElement(srs_id, "geographicflag")
        geographicflag.text = "false"

    def _add_canvas(self) -> None:
        """Add MapCanvas element."""
        # Note: Not needed for rendering, but kept for compatibility
        pass

    def add_step_group(self, step_num: int, step_name: str) -> None:
        """Add a pipeline step group (top level)."""
        # Create group at root level
        group = ET.SubElement(self.layer_tree_group, "layer-tree-group")
        group.set("name", f"Step {step_num} - {step_name}")
        group.set("checked", "Qt::Checked")
        group.set("expanded", "0")
        group.set("groupLayer", "")
        
        # Add custom properties
        custom_props = ET.SubElement(group, "customproperties")
        ET.SubElement(custom_props, "Option")

        # Push to stack
        self.group_stack.append(group)

    def add_method_subgroup(self, method_name: str) -> None:
        """Add a method subgroup under current step."""
        if not self.group_stack:
            raise RuntimeError("No step group active. Call add_step_group() first.")

        current_group = self.group_stack[-1]
        subgroup = ET.SubElement(current_group, "layer-tree-group")
        subgroup.set("name", method_name)
        subgroup.set("checked", "Qt::Checked")
        subgroup.set("expanded", "0")
        subgroup.set("groupLayer", "")
        
        # Add custom properties
        custom_props = ET.SubElement(subgroup, "customproperties")
        ET.SubElement(custom_props, "Option")

        # Push to stack
        self.group_stack.append(subgroup)

    def pop_subgroup(self) -> None:
        """Pop back to parent group."""
        if len(self.group_stack) <= 1:
            raise RuntimeError("Cannot pop root group.")
        self.group_stack.pop()

    def add_raster_layer(
        self,
        tif_path: Path,
        layer_name: str,
        opacity: float = 0.7,
    ) -> None:
        """Add a raster layer."""
        tif_path = Path(tif_path)
        if not tif_path.exists():
            raise FileNotFoundError(f"Raster file not found: {tif_path}")

        # Try to read extent from raster
        if not self.extent:
            try:
                with rasterio.open(tif_path) as src:
                    bounds = src.bounds
                    self.extent = (
                        int(bounds.left),
                        int(bounds.bottom),
                        int(bounds.right),
                        int(bounds.top),
                    )
            except Exception as e:
                print(f"⚠️  Could not read extent from {tif_path}: {e}")

        # Create unique ID with full UUID format
        full_uuid = str(uuid.uuid4())
        layer_id = f"{layer_name}_{full_uuid}"
        self.custom_order.append(layer_id)

        # Determine if this is the first layer in Step 1 (special handling)
        is_step1_first = False
        
        # Make path relative to project base
        try:
            rel_path = "./" + tif_path.relative_to(self.out_base).as_posix()
        except ValueError:
            rel_path = str(tif_path)

        # Add to layer-tree
        current_group = self.group_stack[-1]
        layer_tree_layer = ET.SubElement(current_group, "layer-tree-layer")
        layer_tree_layer.set("id", layer_id)
        layer_tree_layer.set("name", layer_name)
        layer_tree_layer.set("checked", "Qt::Checked")
        layer_tree_layer.set("providerKey", "gdal")
        layer_tree_layer.set("patch_size", "-1,-1")
        layer_tree_layer.set("expanded", "0")
        layer_tree_layer.set("legend_exp", "")
        layer_tree_layer.set("legend_split_behavior", "0")
        layer_tree_layer.set("source", rel_path)

        # Add custom properties
        custom_props = ET.SubElement(layer_tree_layer, "customproperties")
        ET.SubElement(custom_props, "Option")

    def add_vector_layer(self, gpkg_path: Path, layer_name: str, layer_id: Optional[str] = None) -> None:
        """Add a vector layer from GeoPackage."""
        gpkg_path = Path(gpkg_path)
        if not gpkg_path.exists():
            raise FileNotFoundError(f"Vector file not found: {gpkg_path}")

        # Create unique ID with full UUID format if not provided
        if layer_id is None:
            full_uuid = str(uuid.uuid4())
            layer_id = f"{layer_name}_{full_uuid}"
        
        self.custom_order.append(layer_id)

        # Make path relative to project base
        try:
            rel_path = "./" + gpkg_path.relative_to(self.out_base).as_posix()
        except ValueError:
            rel_path = str(gpkg_path)

        # Add to layer-tree
        current_group = self.group_stack[-1]
        layer_tree_layer = ET.SubElement(current_group, "layer-tree-layer")
        layer_tree_layer.set("id", layer_id)
        layer_tree_layer.set("name", layer_name)
        layer_tree_layer.set("checked", "Qt::Checked")
        layer_tree_layer.set("providerKey", "ogr")
        layer_tree_layer.set("patch_size", "0,0")
        layer_tree_layer.set("expanded", "1")
        layer_tree_layer.set("legend_exp", "")
        layer_tree_layer.set("legend_split_behavior", "0")
        layer_tree_layer.set("source", rel_path + "|layername=" + layer_name)

        # Add custom properties
        custom_props = ET.SubElement(layer_tree_layer, "customproperties")
        ET.SubElement(custom_props, "Option")

    def save(self) -> Path:
        """Save project as .qgz file."""
        # Remove old custom-order if it exists
        old_custom_order = self.layer_tree_group.find("custom-order")
        if old_custom_order is not None:
            self.layer_tree_group.remove(old_custom_order)
        
        # Add new custom-order
        custom_order = ET.SubElement(self.layer_tree_group, "custom-order")
        custom_order.set("enabled", "0")
        for layer_id in self.custom_order:
            item = ET.SubElement(custom_order, "item")
            item.text = layer_id

        # Save XML without declaration first
        qgs_file = self.temp_dir_path / "project.qgs"
        tree = ET.ElementTree(self.root)
        tree.write(qgs_file, encoding="UTF-8", xml_declaration=False)

        # Read and add DOCTYPE in correct order
        with open(qgs_file, 'r') as f:
            xml_content = f.read()

        # Remove any existing declaration
        if xml_content.startswith('<?xml'):
            xml_content = xml_content[xml_content.index('?>') + 2:].lstrip()

        with open(qgs_file, 'w') as f:
            f.write('<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n')
            f.write(xml_content)

        # Create .qgz (zip)
        if self.project_path.exists():
            self.project_path.unlink()

        with zipfile.ZipFile(self.project_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(qgs_file, arcname="project.qgs")

        size_kb = self.project_path.stat().st_size / 1024
        print(f"✅ QGIS project saved: {self.project_path} ({size_kb:.1f} KB)")
        return self.project_path

    def cleanup(self) -> None:
        """Remove temporary files."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)


def create_pipeline_project(out_base: Path, project_name: str = "Pipeline") -> QGISProjectBuilder:
    """Create a new QGIS project builder."""
    builder = QGISProjectBuilder(out_base, project_name)
    print(f"📦 QGIS project builder initialized (hierarchical)")
    return builder


if __name__ == "__main__":
    # Test
    test_dir = Path("/tmp/qgis_test")
    test_dir.mkdir(exist_ok=True)

    builder = create_pipeline_project(test_dir)
    print("✅ Project created!")
