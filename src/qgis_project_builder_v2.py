#!/usr/bin/env python3
"""
Simplified QGIS project builder - creates minimal but valid QGIS projects.
Works around XML complexity by using rasterio for metadata.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import rasterio


class SimpleQGISProjectBuilder:
    """Minimal QGIS project builder."""
    
    def __init__(self, out_base: Path, project_name: str = "Pipeline"):
        self.out_base = Path(out_base)
        self.project_name = project_name
        self.project_path = self.out_base / f"{project_name}.qgz"
        self.temp_dir = tempfile.mkdtemp(prefix="qgis_project_")
        self.temp_dir_path = Path(self.temp_dir)
        self.qgs_file = self.temp_dir_path / "project.qgs"
        
        # Will populate extent from first raster
        self.extent = None
        self.layers = []
        
    def add_raster_layer(self, tif_path: Path, layer_name: str, opacity: float = 1.0) -> None:
        """Add a raster layer."""
        if not self.extent:
            # Read extent from first file
            try:
                with rasterio.open(tif_path) as src:
                    bounds = src.bounds
                    self.extent = (int(bounds.left), int(bounds.bottom), int(bounds.right), int(bounds.top))
            except Exception as e:
                print(f"⚠️  Could not read extent: {e}")
                self.extent = (0, 0, 1, 1)
        
        # Make path relative
        try:
            rel_path = Path(tif_path).relative_to(self.out_base)
        except ValueError:
            rel_path = Path(tif_path)
        
        self.layers.append({
            'name': layer_name,
            'path': str(rel_path),
            'opacity': opacity
        })
    
    def save(self) -> Path:
        """Save project as .qgz file."""
        if not self.extent:
            self.extent = (0, 0, 1, 1)
        
        xmin, ymin, xmax, ymax = self.extent
        
        # Create root element
        root = ET.Element("qgis")
        root.set("version", "3.44.0")
        root.set("projectname", self.project_name)
        
        # Title
        title = ET.SubElement(root, "title")
        title.text = f"NMD2 {self.project_name}"
        
        # CRS (EPSG:3006 - Swedish RT90)
        crs_elem = ET.SubElement(root, "crs")
        spatial_ref = ET.SubElement(crs_elem, "spatialrefsys")
        ET.SubElement(spatial_ref, "proj4").text = "+proj=rt90 +lat_0=0 +lon_0=15.80827824305556 +ellps=bessel +units=m +no_defs"
        ET.SubElement(spatial_ref, "srsid").text = "3006"
        ET.SubElement(spatial_ref, "srid").text = "3006"
        ET.SubElement(spatial_ref, "authid").text = "EPSG:3006"
        ET.SubElement(spatial_ref, "description").text = "RT90 2.5 gon V"
        
        # Extent
        extent_elem = ET.SubElement(root, "extent")
        ET.SubElement(extent_elem, "xmin").text = str(xmin)
        ET.SubElement(extent_elem, "ymin").text = str(ymin)
        ET.SubElement(extent_elem, "xmax").text = str(xmax)
        ET.SubElement(extent_elem, "ymax").text = str(ymax)
        
        # ── MAP LAYERS (layer definitions) ──
        maplayers = ET.SubElement(root, "maplayers")
        
        for i, layer_info in enumerate(self.layers):
            maplayer = ET.SubElement(maplayers, "maplayer")
            layer_id = f"layer_{i+1}"
            maplayer.set("id", layer_id)
            maplayer.set("type", "raster")
            maplayer.set("refreshOnNotifyEnabled", "0")
            maplayer.set("refreshNotifyInterval", "0")
            maplayer.set("hasScaleBasedVisibilityFlag", "0")
            maplayer.set("autoRefreshEnabled", "0")
            maplayer.set("autoRefreshInterval", "0")
            maplayer.set("maxScale", "0")
            maplayer.set("minScale", "1e+08")
            maplayer.set("styleCategories", "AllStyleCategories")
            maplayer.set("validate", "1")
            
            # Name
            name = ET.SubElement(maplayer, "name")
            name.text = layer_info['name']
            
            # Datasource
            datasource = ET.SubElement(maplayer, "datasource")
            datasource.text = layer_info['path']
            
            # Provider
            provider = ET.SubElement(maplayer, "provider")
            provider.text = "gdal"
            
            # Extent
            extent = ET.SubElement(maplayer, "extent")
            ET.SubElement(extent, "xmin").text = str(xmin)
            ET.SubElement(extent, "ymin").text = str(ymin)
            ET.SubElement(extent, "xmax").text = str(xmax)
            ET.SubElement(extent, "ymax").text = str(ymax)
            
            # CRS
            srs = ET.SubElement(maplayer, "srs")
            spatial_ref = ET.SubElement(srs, "spatialrefsys")
            ET.SubElement(spatial_ref, "authid").text = "EPSG:3006"
            
            # Opacity
            opacity = ET.SubElement(maplayer, "layerOpacity")
            opacity.text = str(layer_info['opacity'])
        
        # ── LAYER TREE (hierarki i lagerpanelen) - KRITISK! ──
        layer_tree = ET.SubElement(root, "layer-tree-group")
        layer_tree.set("checked", "Qt::Checked")
        layer_tree.set("name", self.project_name)
        layer_tree.set("expanded", "1")
        
        for i, layer_info in enumerate(self.layers):
            layer_id = f"layer_{i+1}"
            layer_tree_layer = ET.SubElement(layer_tree, "layer-tree-layer")
            layer_tree_layer.set("id", layer_id)
            layer_tree_layer.set("name", layer_info['name'])
            layer_tree_layer.set("source", layer_info['path'])
            layer_tree_layer.set("checked", "Qt::Checked")
            layer_tree_layer.set("providerKey", "gdal")
            layer_tree_layer.set("expanded", "0")
        
        # ── LEGEND ──
        legend = ET.SubElement(root, "legend")
        legend.set("updateDrawingOrder", "true")
        
        for i, layer_info in enumerate(self.layers):
            layer_id = f"layer_{i+1}"
            legend_layer = ET.SubElement(legend, "legendlayer")
            legend_layer.set("open", "false")
            legend_layer.set("name", layer_info['name'])
            legend_layer.set("drawingOrder", str(i))
            legend_item = ET.SubElement(legend_layer, "legenditem")
            legend_item.text = layer_info['name']
        
        # Write XML
        tree = ET.ElementTree(root)
        tree.write(self.qgs_file, encoding="utf-8", xml_declaration=True)
        
        # Create .qgz (zip)
        if self.project_path.exists():
            self.project_path.unlink()
        
        with zipfile.ZipFile(self.project_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(self.qgs_file, arcname="project.qgs")
        
        print(f"✅ QGIS project saved: {self.project_path} ({self.project_path.stat().st_size} bytes)")
        return self.project_path
    
    def cleanup(self) -> None:
        """Remove temporary files."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)


def create_pipeline_project(out_base: Path) -> SimpleQGISProjectBuilder:
    """Create a new QGIS project builder."""
    builder = SimpleQGISProjectBuilder(out_base, project_name="Pipeline")
    print(f"📦 QGIS project builder initialized")
    return builder


if __name__ == "__main__":
    # Test
    import tempfile
    test_dir = Path(tempfile.gettempdir()) / "test_qgis_v2"
    test_dir.mkdir(exist_ok=True)
    
    builder = create_pipeline_project(test_dir)
    builder.add_raster_layer(Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5/tiles/NMD2023bas_tile_r000_c020.tif"), "Tile 1", 0.7)
    builder.save()
    builder.cleanup()
    
    print("✅ Test completed!")
