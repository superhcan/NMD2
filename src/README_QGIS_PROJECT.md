# QGIS Project Builder

Skapar dinamiska QGIS-projekt som växer tillsammans med pipelinen.

## Projektstruktur

Projektet organiseras hierarkiskt med **steg** och **metod-undergrupper**:

```
📦 NMD2 Pipeline Project
├── 🗂️ Step 1 - Split Tiles
├── 🗂️ Step 2 - Protected Classes
├── 🗂️ Step 3 - Landscape Extract
├── 🗂️ Step 4 - Fill Islands
├── 🗂️ Step 5 - Generalized
│   ├── 🗂️ Sieve Conn4
│   │   ├── mmu002
│   │   ├── mmu004
│   │   ├── mmu008
│   │   └── ...
│   ├── 🗂️ Sieve Conn8
│   │   ├── mmu002
│   │   ├── mmu004
│   │   └── ...
│   ├── 🗂️ Modal Filter
│   │   ├── k03
│   │   ├── k05
│   │   ├── k07
│   │   ├── k11
│   │   ├── k13
│   │   └── k15
│   └── 🗂️ Semantic
│       ├── mmu002
│       ├── mmu004
│       └── ...
├── 🗂️ Step 6 - Vectorized
└── 🗂️ Step 7 - Simplified (Mapshaper)
    ├── 🗂️ p90% (minimal)
    ├── 🗂️ p75% (light)
    ├── 🗂️ p50% (moderate)
    └── 🗂️ p25% (aggressive)
```

## Användning

```python
from qgis_project_builder import create_pipeline_project
from pathlib import Path

# Initialisera projekt
out_base = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo_v2")
project = create_pipeline_project(out_base)

# Step 1: Split Tiles
project.add_step_group(1, "Split Tiles")
for tile_path in tile_paths:
    project.add_raster_layer(tile_path, tile_path.stem)

# Step 5: Generalized (med subgrupper)
project.add_step_group(5, "Generalized")

# Sieve Conn4
project.add_method_subgroup("Sieve Conn4")
for mmu, tiles in sieve_conn4_by_mmu.items():
    for tile in tiles:
        project.add_raster_layer(tile, tile.stem, opacity=0.7)
project.pop_subgroup()

# Sieve Conn8 (samma mönster)
project.add_method_subgroup("Sieve Conn8")
# ... lägg till lager ...
project.pop_subgroup()

# Modal Filter
project.add_method_subgroup("Modal Filter")
# ... lägg till lager ...
project.pop_subgroup()

# Semantic
project.add_method_subgroup("Semantic")
# ... lägg till lager ...
project.pop_subgroup()

# Step 7: Simplified (Mapshaper)
project.add_step_group(7, "Simplified (Mapshaper)")

for level, gpkg_path in simplified_levels.items():
    level_name = f"p{level}% ({description})"
    project.add_method_subgroup(level_name)
    project.add_vector_layer(gpkg_path, f"Simplified p{level}%")
    project.pop_subgroup()

# Spara projekt
project.save()
project.cleanup()
```

## API-referens

### `QGISProjectBuilder`

#### `__init__(out_base, project_name="Pipeline")`
Initialisera en ny QGIS-projektbyggare.

#### `add_step_group(step_num, step_name)`
Lägg till en steg-grupp (högsta nivån).

#### `add_method_subgroup(method_name)`
Lägg till en metod-undergrupp under nuvarande steg.

#### `pop_subgroup()`
Gå tillbaka till föräldragruppen.

#### `add_raster_layer(tif_path, layer_name, opacity=1.0)`
Lägg till ett rasterlayer.

#### `add_vector_layer(gpkg_path, layer_name, layer_id=None)`
Lägg till ett vektorlayer från GeoPackage.

#### `save()`
Spara projektet som `.qgz`-fil.

#### `cleanup()`
Rensa temporära filer.

## Integration i pipelinen

För att integreras i `pipeline_1024_halo.py`:

```python
from qgis_project_builder import create_pipeline_project

# I __main__:
project_builder = create_pipeline_project(OUT_BASE)

# Efter Step 1:
project_builder.add_step_group(1, "Split Tiles")
for tile in tile_paths:
    project_builder.add_raster_layer(tile, tile.stem)
project_builder.save()

# ... och så vidare för varje steg ...
```

## Notering

- Projektet sparas efter varje steg automatiskt
- Lager läggs till i realtid under körning
- Relative paths används för portabilitet
- Alla raster-lager får 70% transparens för överlappning-visning
