#!/usr/bin/env python3
"""
QGIS Project Builder v3 - baseras på en template-fil som fungerar
Kopiera bara pipeline.qgs som template och uppdatera lagren.
"""

import shutil
import tempfile
import zipfile
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

import rasterio


class TemplateBasedQGISBuilder:
    """Baseras på en fungerande QGIS-projektfil som template."""
    
    TEMPLATE_FILE = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v2/pipeline.qgs")
    
    def __init__(self, out_base: Path, project_name: str = "Pipeline"):
        self.out_base = Path(out_base)
        self.project_name = project_name
        self.project_path = self.out_base / f"{project_name}.qgz"
        self.temp_dir = tempfile.mkdtemp(prefix="qgis_project_")
        self.temp_dir_path = Path(self.temp_dir)
        
        # Load template
        if not self.TEMPLATE_FILE.exists():
            raise FileNotFoundError(f"Template file not found: {self.TEMPLATE_FILE}")
        
        # Parse template
        self.tree = ET.parse(self.TEMPLATE_FILE)
        self.root = self.tree.getroot()
        
        # Extent
        self.extent = None
    
    def add_layer(self, tif_path: Path, layer_name: str, opacity: float = 1.0) -> None:
        """Add a raster layer - for now just a placeholder."""
        if not self.extent:
            try:
                with rasterio.open(tif_path) as src:
                    bounds = src.bounds
                    self.extent = (int(bounds.left), int(bounds.bottom), int(bounds.right), int(bounds.top))
            except Exception as e:
                print(f"⚠️  Could not read extent: {e}")
    
    def add_raster_layer(self, tif_path: Path, layer_name: str, opacity: float = 1.0) -> None:
        """Alias for add_layer for backwards compatibility."""
        self.add_layer(tif_path, layer_name, opacity)
    
    def save(self) -> Path:
        """Save project using template structure."""
        
        # Update project extent if we have it
        if self.extent:
            xmin, ymin, xmax, ymax = self.extent
            
            # Find extent element (might be in mapCanvass or other places)
            for extent_elem in self.root.iter("extent"):
                try:
                    extent_elem.find("xmin").text = str(xmin)
                    extent_elem.find("ymin").text = str(ymin)
                    extent_elem.find("xmax").text = str(xmax)
                    extent_elem.find("ymax").text = str(ymax)
                except:
                    pass
        
        # Save XML without declaration first
        qgs_file = self.temp_dir_path / "project.qgs"
        self.tree.write(qgs_file, encoding="UTF-8", xml_declaration=False)
        
        # Add XML declaration and DOCTYPE in correct order
        with open(qgs_file, 'r') as f:
            xml_content = f.read()
        
        with open(qgs_file, 'w') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write("<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n")
            f.write(xml_content)
        
        # Create .qgz (zip)
        if self.project_path.exists():
            self.project_path.unlink()
        
        with zipfile.ZipFile(self.project_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(qgs_file, arcname="project.qgs")
        
        size_mb = self.project_path.stat().st_size / 1024
        print(f"✅ QGIS project saved: {self.project_path} ({size_mb:.1f} KB)")
        return self.project_path
    
    def cleanup(self) -> None:
        """Remove temporary files."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)


def create_pipeline_project(out_base: Path) -> TemplateBasedQGISBuilder:
    """Create a new QGIS project builder."""
    builder = TemplateBasedQGISBuilder(out_base, project_name="Pipeline")
    print(f"📦 QGIS project builder initialized (template-based)")
    return builder


if __name__ == "__main__":
    test_dir = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v5")
    
    builder = create_pipeline_project(test_dir)
    builder.save()
    builder.cleanup()
    
    print("✅ Test completed!")
