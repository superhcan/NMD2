#!/usr/bin/env python3
"""
qgis_project_builder.py — Build QGIS projects dynamically during pipeline execution.

Skapar ett hierarkiskt QGIS-projekt med steg och subgrupper för metoder.
Projektet uppdateras i realtid när pipelinen kör.

Projektstruktur:
  Step 1 - Split Tiles
  Step 2 - Protected Classes
  Step 3 - Landscape Extract
  Step 4 - Fill Islands
  Step 5 - Generalized
    ├── Sieve Conn4 (mmu002, mmu004, mmu008, ...)
    ├── Sieve Conn8 (mmu002, mmu004, mmu008, ...)
    ├── Modal Filter (k03, k05, k07, k11, k13, k15)
    └── Semantic (mmu002, mmu004, mmu008, ...)
  Step 6 - Vectorized
  Step 7 - Simplified (Mapshaper)
    ├── p90% simplification
    ├── p75% simplification
    ├── p50% simplification
    └── p25% simplification
"""

import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime


class QGISProjectBuilder:
    """Bygger och hanterar QGIS-projekt med dynamisk uppdatering."""
    
    def __init__(self, out_base: Path, project_name: str = "Pipeline"):
        """
        Initialisera QGIS-projektbyggare.
        
        Args:
            out_base: Basutgångskatalog (där log/, summary/, osv finns)
            project_name: Projektnamn
        """
        self.out_base = Path(out_base)
        self.project_name = project_name
        self.project_path = self.out_base / f"{project_name}_Pipeline.qgz"
        
        # Skapa projekt-katalog för temporär arbete
        self.temp_dir = tempfile.mkdtemp(prefix="qgis_project_")
        self.temp_dir_path = Path(self.temp_dir)
        self.qgs_file = self.temp_dir_path / "project.qgs"
        
        # Layer tracking
        self.layer_count = 0
        self.group_stack = []  # Stack för nested groups
        
        # Initialize XML structure
        self.root = self._create_root()
        self.layer_tree_group = self.root.find(".//layer-tree-group")
        self.map_layers = self.root.find("./maplayers")
        self.layer_tree_group_stack = [self.layer_tree_group]  # Stack för grupper
        
    def _create_root(self) -> ET.Element:
        """Skapa QGIS-projektets XML-rot."""
        root = ET.Element("qgis", version="3.32.0", projectname=self.project_name)
        
        # Metadata
        title = ET.SubElement(root, "title")
        title.text = f"NMD2 {self.project_name}"
        
        # Extent
        extent = ET.SubElement(root, "extent")
        ET.SubElement(extent, "xmin").text = "0"
        ET.SubElement(extent, "ymin").text = "0"
        ET.SubElement(extent, "xmax").text = "1"
        ET.SubElement(extent, "ymax").text = "1"
        
        # CRS
        crs = ET.SubElement(root, "crs")
        spatial_ref_sys = ET.SubElement(crs, "spatialrefsys")
        ET.SubElement(spatial_ref_sys, "proj4").text = "+proj=rt90 +lat_0=0 +lon_0=15.80827824305556"
        ET.SubElement(spatial_ref_sys, "authid").text = "EPSG:3006"
        
        # Legend
        legend = ET.SubElement(root, "legend", updateDrawingOrder="true")
        
        # Layer tree
        layer_tree = ET.SubElement(root, "layer-tree-group", checked="Qt::Checked", name="NMD2 Pipeline", expanded="1")
        ET.SubElement(layer_tree, "customproperties")
        
        # Map layers container
        ET.SubElement(root, "maplayers")
        
        # Composer (for printing)
        ET.SubElement(root, "Composer")
        
        return root
    
    def add_step_group(self, step_num: int, step_name: str) -> None:
        """
        Lägg till en steg-grupp (t.ex. "Step 1 - Split Tiles").
        
        Args:
            step_num: Stegnummer (1-7)
            step_name: Stegbeskrivning
        """
        group_name = f"Step {step_num} - {step_name}"
        group_elem = ET.SubElement(
            self.layer_tree_group,
            "layer-tree-group",
            checked="Qt::Checked",
            name=group_name,
            expanded="1"
        )
        ET.SubElement(group_elem, "customproperties")
        
        # Spara gruppen för senare undergrupper
        self.layer_tree_group_stack = [self.layer_tree_group, group_elem]
    
    def add_method_subgroup(self, method_name: str) -> None:
        """
        Lägg till en metod-undergrupp under nuvarande steg.
        
        Args:
            method_name: Metodnamn (t.ex. "Sieve Conn4", "Modal Filter")
        """
        # Använd den senaste steg-gruppen
        parent_group = self.layer_tree_group_stack[-1]
        
        subgroup_elem = ET.SubElement(
            parent_group,
            "layer-tree-group",
            checked="Qt::Checked",
            name=method_name,
            expanded="0"
        )
        ET.SubElement(subgroup_elem, "customproperties")
        
        # Uppdatera stack för lager
        self.layer_tree_group_stack.append(subgroup_elem)
    
    def pop_subgroup(self) -> None:
        """Gå tillbaka till föräldragruppen efter att ha lagt till undergrupp-lager."""
        if len(self.layer_tree_group_stack) > 2:  # Behåll minst root + step
            self.layer_tree_group_stack.pop()
    
    def add_raster_layer(self, tif_path: Path, layer_name: str, opacity: float = 1.0) -> None:
        """
        Lägg till rasterlager.
        
        Args:
            tif_path: Sökväg till TIF-fil
            layer_name: Lagrets namn i QGIS
            opacity: Genomskinlighet (0.0-1.0)
        """
        self.layer_count += 1
        layer_id = f"layer_{self.layer_count}"
        
        # Lägg till i layer-tree
        current_group = self.layer_tree_group_stack[-1]
        layer_tree_layer = ET.SubElement(
            current_group,
            "layer-tree-layer",
            id=layer_id,
            name=layer_name,
            source=str(tif_path),
            checked="Qt::Checked",
            providerKey="gdal",
            expanded="0"
        )
        ET.SubElement(layer_tree_layer, "customproperties")
        
        # Lägg till i maplayers
        maplayer = ET.SubElement(
            self.map_layers,
            "maplayer",
            type="raster",
            hasScaleBasedVisibilityFlag="0",
            maxScale="0",
            minScale="1e+08"
        )
        
        ET.SubElement(maplayer, "extent")
        maplayer_name = ET.SubElement(maplayer, "name")
        maplayer_name.text = layer_name
        
        datasource = ET.SubElement(maplayer, "datasource")
        datasource.text = str(tif_path)
        
        provider = ET.SubElement(maplayer, "provider", key="gdal")
        provider.text = "gdal"
        
        # Opacity
        blending_mode = ET.SubElement(maplayer, "blendMode")
        blending_mode.text = "0"
        
        layer_opacity = ET.SubElement(maplayer, "layerOpacity")
        layer_opacity.text = str(opacity)
    
    def add_vector_layer(self, gpkg_path: Path, layer_name: str, layer_id: str = None) -> None:
        """
        Lägg till vektor-lager (från GeoPackage).
        
        Args:
            gpkg_path: Sökväg till GeoPackage
            layer_name: Lagrets namn i QGIS
            layer_id: Layer-ID från GeoPackage (default: första lagret)
        """
        if layer_id is None:
            layer_id = "markslag"
        
        self.layer_count += 1
        layer_qgis_id = f"layer_{self.layer_count}"
        
        datasource_str = f"{gpkg_path}|layername={layer_id}"
        
        # Lägg till i layer-tree
        current_group = self.layer_tree_group_stack[-1]
        layer_tree_layer = ET.SubElement(
            current_group,
            "layer-tree-layer",
            id=layer_qgis_id,
            name=layer_name,
            source=datasource_str,
            checked="Qt::Checked",
            providerKey="ogr",
            expanded="0"
        )
        ET.SubElement(layer_tree_layer, "customproperties")
        
        # Lägg till i maplayers
        maplayer = ET.SubElement(
            self.map_layers,
            "maplayer",
            type="vector",
            hasScaleBasedVisibilityFlag="0",
            maxScale="0",
            minScale="1e+08"
        )
        
        maplayer_name = ET.SubElement(maplayer, "name")
        maplayer_name.text = layer_name
        
        datasource = ET.SubElement(maplayer, "datasource")
        datasource.text = datasource_str
        
        provider = ET.SubElement(maplayer, "provider", key="ogr")
        provider.text = "ogr"
        
        # Geometry type
        geom_type = ET.SubElement(maplayer, "geometryType")
        geom_type.text = "Polygon"
    
    def save(self) -> Path:
        """
        Spara projektet som .qgz-fil.
        
        Returns:
            Sökväg till sparad .qgz-fil
        """
        # Spara XML
        tree = ET.ElementTree(self.root)
        tree.write(self.qgs_file, encoding="utf-8", xml_declaration=True)
        
        # Skapa .qgz (ZIP) med projekt.qgs + stilfil
        if self.project_path.exists():
            self.project_path.unlink()
        
        # Skapa temporär zip
        shutil.make_archive(
            str(self.project_path.with_suffix("")),  # Base name utan .qgz
            "zip",
            self.temp_dir_path
        )
        
        # Byt namn från .zip till .qgz
        zip_file = self.project_path.with_suffix(".zip")
        if zip_file.exists():
            zip_file.rename(self.project_path)
        
        print(f"✅ QGIS-projekt sparad: {self.project_path}")
        return self.project_path
    
    def cleanup(self) -> None:
        """Rensa temporära filer."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)


# ════════════════════════════════════════════════════════════════════════════════


def create_pipeline_project(out_base: Path) -> QGISProjectBuilder:
    """
    Skapa ett nytt QGIS-projekt för denna pipeline-körning.
    
    Args:
        out_base: Basutgångskatalog
    
    Returns:
        QGISProjectBuilder-instans
    """
    builder = QGISProjectBuilder(out_base, project_name="Pipeline")
    print(f"📦 Initialiserat QGIS-projekt: {builder.project_path}")
    return builder


if __name__ == "__main__":
    # TEST
    test_out = Path("/tmp/test_qgis_project")
    test_out.mkdir(exist_ok=True)
    
    builder = create_pipeline_project(test_out)
    
    # Step 1
    builder.add_step_group(1, "Split Tiles")
    
    # Step 5 - Generalized (med subgrupper)
    builder.add_step_group(5, "Generalized")
    builder.add_method_subgroup("Sieve Conn4")
    builder.pop_subgroup()
    builder.add_method_subgroup("Sieve Conn8")
    builder.pop_subgroup()
    builder.add_method_subgroup("Modal Filter")
    builder.pop_subgroup()
    builder.add_method_subgroup("Semantic")
    builder.pop_subgroup()
    
    # Step 7 - Simplified (Mapshaper med simplifieringsnivåer)
    builder.add_step_group(7, "Simplified (Mapshaper)")
    builder.add_method_subgroup("p90% (minimal)")
    builder.pop_subgroup()
    builder.add_method_subgroup("p75% (light)")
    builder.pop_subgroup()
    builder.add_method_subgroup("p50% (moderate)")
    builder.pop_subgroup()
    builder.add_method_subgroup("p25% (aggressive)")
    builder.pop_subgroup()
    
    builder.save()
    builder.cleanup()
    
    print("✅ Test slutfört!")
