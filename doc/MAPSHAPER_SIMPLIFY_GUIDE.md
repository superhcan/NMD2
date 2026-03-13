# Mapshaper -simplify Command: Comprehensive Guide

## Overview
Mapshaper provides three main methods to control simplification amount: **percentage**, **resolution**, and **interval**. Each has different use cases and advantages.

---

## 1. Parameter Differences

### `percentage=X` - Point Retention Method
**Purpose**: Retain a specific percentage of removable vertices.

**Syntax**:
```bash
mapshaper input.geojson -simplify 10% -o output.geojson
mapshaper input.geojson -simplify percentage=10 -o output.geojson  # 0-1 scale
```

**Characteristics**:
- Retains 10% of removable vertices (meaning 90% of non-essential points are removed)
- Accepts values: `0%-100%` or `0-1` (decimal)
- Independent of coordinate system or units
- **Best for**: Uniform simplification across varied geometries
- **Gotcha**: Same percentage might produce very different results on features of different complexity

**Use Case Example**:
```bash
# Keep features similarly simplified regardless of scale
mapshaper counties.shp -simplify 15% -o simplified.shp
```

---

### `resolution=X` - Output Resolution Method  
**Purpose**: Specify desired output resolution for display/output.

**Syntax**:
```bash
mapshaper input.geojson -simplify resolution=1000 -o output.geojson
mapshaper input.geojson -simplify resolution=1000x800 -o output.geojson
```

**Characteristics**:
- Treats coordinates as if they'll be rendered at this resolution
- **Units depend on coordinate system**:
  - **Projected coordinates** (e.g., EPSG:3006): Units are in projection units (meters for most European projections)
  - **Geographic coordinates** (lat/lon): Uses meters when `planar` is NOT specified; uses degrees when `planar` IS specified
- Calculates simplification to match expected output resolution
- **Best for**: Output-size aware simplification (e.g., for web display)
- **Gotcha**: Very sensitive to coordinate system; must understand your projection units

**Use Case Example** (Your project's case):
```bash
# For EPSG:3006 (Swedish projection, meters)
# This means simplify to meters resolution in your projected coordinate space
mapshaper modal_k15.geojson -simplify resolution=2 planar -o output.geojson    # 2 meters
mapshaper modal_k15.geojson -simplify resolution=5 planar -o output.geojson    # 5 meters  
mapshaper modal_k15.geojson -simplify resolution=10 planar -o output.geojson   # 10 meters
mapshaper modal_k15.geojson -simplify resolution=20 planar -o output.geojson   # 20 meters
```

---

### `interval=X` - Distance Threshold Method
**Purpose**: Remove points within a specific distance tolerance.

**Syntax**:
```bash
mapshaper input.geojson -simplify interval=100 -o output.geojson
mapshaper provinces.shp -simplify dp interval=100 -o simplified.shp
```

**Characteristics**:
- Direct distance threshold in coordinate system units
- **Units depend on coordinate system**:
  - **Projected coordinates** (e.g., EPSG:3006): Meters
  - **Geographic coordinates** (lat/lon): Meters when simplifying in 3D space (default); degrees when `planar` is used
- Most explicit/predictable parameter
- **Best for**: Douglas-Peucker simplification (DP algorithm respects this threshold directly)
- **Historical note**: Used in official Mapshaper examples with DP

**Use Case Example**:
```bash
# Use Douglas-Peucker with 100-meter tolerance
mapshaper states.shp -simplify dp interval=100 -o simplified.shp

# For projected data (meters)
mapshaper modal_k15.geojson -simplify dp interval=5 planar -o output.geojson
```

---

## 2. How Resolution Parameter Works

### Resolution Calculation Logic
- Mapshaper treats `resolution=X` as the expected output resolution for rendering
- Internally calculates what simplification level would be appropriate for this display resolution
- **NOT the same as**: "simplify to X units"; rather "simplify as if output will be at resolution X"

### Understanding Units

**Projected Data (EPSG:3006 - Swedish Region)**:
```
Your coordinates are in meters
resolution=2    → Simplify assuming 2-meter output resolution
resolution=5    → Simplify assuming 5-meter output resolution  
resolution=10   → Simplify assuming 10-meter output resolution
resolution=20   → Simplify assuming 20-meter output resolution
```

**Geographic Data (WGS84 lat/lon WITHOUT planar)**:
```
resolution=0.001 → ~111 meters simplification (0.001 degrees ≈ 111 meters)
resolution=0.01  → ~1111 meters simplification
resolution=0.1   → ~11 kilometers simplification
(Approximate conversion: degrees × 111,000 = meters at equator)
```

**Geographic Data (WGS84 WITH planar flag)**:
```
-simplify resolution=0.001 planar  → Treats degrees as flat coordinates
(Uses straightforward Cartesian distance calculation)
```

---

## 3. Effects of Different Tolerance/Resolution Values

### Simplification Progression (Increasing Removal of Detail)

For dataset with EPSG:3006 projection:

```
Original File:       1,000,000 vertices, 50 MB
├─ resolution=1     → Very aggressive (smallest features removed)
├─ resolution=2     → Heavy simplification (coarse details only)
├─ resolution=5     → Moderate simplification (visible loss of detail)
├─ resolution=10    → Light simplification (still fairly detailed)
├─ resolution=20    → Minimal simplification (preserves most features)
└─ resolution=50    → Almost no simplification
```

### Complexity vs Result Quality

**Low Resolution Values** (aggressive simplification):
```
Pros:   • Smaller file sizes
        • Faster processing
        • Web-friendly

Cons:   • Loss of fine geographic detail
        • Potential topology issues
        • Less accurate representation
```

**High Resolution Values** (minimal simplification):
```
Pros:   • Better accuracy
        • Topology preservation
        • Retains small features

Cons:   • Larger file sizes  
        • More complex boundaries
        • Slower performance
```

---

## 4. Creating Multiple Simplified Outputs (Varying Levels)

### Example 1: Loop Through Different Resolutions

```bash
#!/bin/bash
INPUT="modal_k15_original.geojson"
OUTPUT_DIR="simplified_outputs"

mkdir -p "$OUTPUT_DIR"

for resolution in 1 2 5 10 20 50; do
    OUTPUT="$OUTPUT_DIR/modal_k15_res${resolution}.geojson"
    echo "Simplifying with resolution=$resolution..."
    mapshaper "$INPUT" -simplify resolution=$resolution planar \
        format=geojson -o "$OUTPUT"
done
```

### Example 2: Python Script (Like Your Current Project)

```python
#!/usr/bin/env python3
"""
Generate multiple simplified outputs at different resolution levels
"""
import subprocess
from pathlib import Path

def simplify_at_resolutions(input_file, output_dir, resolutions=[1, 2, 5, 10, 20]):
    """
    Create multiple simplified versions at different resolution levels.
    
    Args:
        input_file: Path to input GeoJSON/Shapefile
        output_dir: Directory for outputs
        resolutions: List of resolution values to test
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for res in resolutions:
        output_file = output_path / f"simplified_res{res}.geojson"
        
        cmd = [
            "mapshaper",
            str(input_file),
            "-simplify",
            f"resolution={res}",
            "planar",
            "-o",
            "format=geojson",
            str(output_file)
        ]
        
        print(f"Processing resolution={res}...", end=" ", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            size_mb = output_file.stat().st_size / 1024 / 1024
            print(f"✓ {size_mb:.1f} MB")
        else:
            print(f"✗ Failed: {result.stderr}")

# Usage
if __name__ == "__main__":
    input_geojson = "modal_k15_combined.geojson"
    simplified_resolution_values = [1, 2, 5, 10, 20, 50]
    
    simplify_at_resolutions(
        input_geojson,
        "pipeline_outputs/resolutions",
        simplified_resolution_values
    )
```

### Example 3: Batch Processing with Topology Preservation

```bash
#!/bin/bash
# Create multiple outputs preserving topology

INPUT="$1"
OUTPUT_DIR="${2:-.}"

for tolerance in 2 5 10 20; do
    echo "Creating simplified version: tolerance=${tolerance}m"
    
    mapshaper "$INPUT" \
        -simplify resolution=$tolerance planar keep-shapes \
        -o format=geojson \
        "$OUTPUT_DIR/simplified_${tolerance}m.geojson"
done

echo "Completed! All files in: $OUTPUT_DIR"
```

---

## 5. Gotchas & Common Mistakes

### ❌ Gotcha #1: Confusing Resolution with Interval

```bash
# WRONG - these do NOT mean the same thing:
mapshaper data.geojson -simplify resolution=10 -o output1.geojson
mapshaper data.geojson -simplify interval=10 -o output2.geojson
# ↑ These produce very different results!

# resolution=10 → "Simplify as if 10-unit output"
# interval=10   → "Remove points within 10-unit distance" (stricter DP bound)
```

### ❌ Gotcha #2: Wrong Units for Geographic Coordinates

```bash
# WRONG - treating degrees as meters:
mapshaper world.geojson -simplify resolution=0.001 -o output.geojson
# ↑ This produces almost NO simplification (0.001 degrees ≈ 111 meters)

# CORRECT - either reproject to meters or use planar appropriately:
mapshaper world.geojson -simplify resolution=100 interval=100 -o output.geojson
# OR use very small degree values
mapshaper world.geojson -simplify resolution=0.0001 -o output.geojson
```

### ❌ Gotcha #3: Forgetting `planar` Flag with Projected Data

```bash
# Your case with EPSG:3006:
mapshaper data.geojson -simplify resolution=5 -o output.geojson
# Without planar flag, it may treat differently than expected

# CORRECT:
mapshaper data.geojson -simplify resolution=5 planar -o output.geojson
```

### ❌ Gotcha #4: Losing Polygons at High Simplification

```bash
# WRONG - polygons may disappear:
mapshaper polygons.geojson -simplify resolution=1 -o output.geojson
# Some polygons might become too small and vanish

# CORRECT - preserve polygon shapes:
mapshaper polygons.geojson -simplify resolution=1 keep-shapes -o output.geojson
```

### ❌ Gotcha #5: Not Specifying Coordinate System

```bash
# Ambiguous - Mapshaper might guess wrong:
mapshaper data.geojson -simplify resolution=10

# CORRECT - explicitly specify if geographic needs special handling:
mapshaper data.geojson -simplify resolution=10 planar  # Treat as Cartesian
# OR reproject first:
mapshaper data.geojson -proj EPSG:3006 -simplify resolution=10
```

### ❌ Gotcha #6: DP vs Default Algorithm with Resolution

```bash
# Confusion about algorithms:
mapshaper data.geojson -simplify resolution=10 -o default_algo.geojson
mapshaper data.geojson -simplify dp resolution=10 -o dp_algo.geojson
# Different simplification algorithms from same resolution value
```

### ✅ Best Practices to Avoid Gotchas

1. **Always test with small samples first**
   ```bash
   mapshaper sample_10features.geojson -simplify resolution=5 -o test.geojson
   ```

2. **Use explicit algorithm choice**
   ```bash
   # Be explicit about which simplification method
   mapshaper data.geojson -simplify weighted resolution=10 -o output.geojson  # Visvalingam (default)
   mapshaper data.geojson -simplify dp resolution=10 -o output.geojson        # Douglas-Peucker
   ```

3. **Document coordinate system in commands**
   ```bash
   # Comment in scripts what your assumption is
   mapshaper data_epsg3006.geojson -simplify resolution=5 planar  # Units: meters, projection: EPSG:3006
   ```

4. **Use `stats` flag to understand results**
   ```bash
   mapshaper data.geojson -simplify resolution=5 stats -o output.geojson
   # Shows detailed statistics about what was removed
   ```

5. **Compare outputs before processing large batches**
   ```bash
   # Test on sample first
   mapshaper large_file.geojson -filter 'this.id < 100' \
       -simplify resolution=5 -o sample_test.geojson
   ```

---

## 6. Simplification Methods

### Default: Weighted Visvalingam
```bash
mapshaper data.geojson -simplify resolution=10 -o output.geojson
# Uses effective area metric with weight favoring acute angles
# Result: Smoother boundaries, better visual appearance
```

### Unweighted Visvalingam
```bash
mapshaper data.geojson -simplify visvalingam resolution=10 -o output.geojson
# Pure effective area metric, less preference for smooth angles
```

### Douglas-Peucker (DP/RDP)
```bash
mapshaper data.geojson -simplify dp interval=10 -o output.geojson
# Points remain within specified distance of original line
# Result: May have spikes at high simplification, but bounded tolerance
```

### Comparison from Documentation
- **Weighted Visvalingam** (Default): Better for map rendering, smoother results
- **Douglas-Peucker**: Better for tolerances that must be respected (e.g., official specifications)

---

## 7. Real-World Example for Your NMD2 Project

Based on your `simplify_mapshaper.py` working with EPSG:3006 (Swedish projection):

```python
#!/usr/bin/env python3
"""
NMD2 Exemplar: Simplify at multiple resolutions for different use cases
"""
import subprocess
from pathlib import Path

def create_mmu_variants(input_geojson, output_dir):
    """
    Create simplified versions representing different Minimum Mapping Units (MMU).
    MMU = Minimum area that must be mapped separately (common GIS concept)
    
    For raster land cover like NMD2:
    - mmu001 = Most detailed (1 hectare regions)
    - mmu002 = 2 hectare min
    - mmu005 = 5 hectare min
    - etc.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Resolution corresponds roughly to cell size in output
    # EPSG:3006 uses meters, so higher values = coarser output
    mmu_configs = [
        {"name": "mmu001", "resolution": 1},   # ~1m resolution (very fine)
        {"name": "mmu002", "resolution": 2},   # ~2m resolution
        {"name": "mmu005", "resolution": 5},   # ~5m resolution  
        {"name": "mmu010", "resolution": 10},  # ~10m resolution
        {"name": "mmu020", "resolution": 20},  # ~20m resolution
        {"name": "mmu050", "resolution": 50},  # ~50m resolution
    ]
    
    for config in mmu_configs:
        output_file = output_path / f"nmd2023_modal_{config['name']}.geojson"
        
        cmd = [
            "mapshaper", str(input_geojson),
            "-simplify", 
            f"resolution={config['resolution']} planar keep-shapes",
            "-o", "format=geojson",
            str(output_file)
        ]
        
        print(f"Creating {config['name']} (resolution={config['resolution']}m)... ", end="", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            size_mb = output_file.stat().st_size / 1e6
            print(f"✓ {size_mb:.1f} MB")
        else:
            print(f"✗ Error: {result.stderr}")

# Usage
create_mmu_variants(
    "modal_k15_original.geojson",
    "output/mmu_variants"
)
```

---

## Summary Table

| Parameter | Units | Best For | Gotchas |
|-----------|-------|----------|---------|
| `percentage=X` | None (%) | Uniform simplification | Same % ≠ same detail reduction |
| `resolution=X` | Projection units (usually m or degrees) | Output-aware simplification | Must match coordinate system; different units depending on projection |
| `interval=X` | Projection units (usually m or degrees) | Douglas-Peucker with known tolerance | Direct DP use; units must match your data |

---

## Quick Reference: Your EPSG:3006 Project

```bash
# For your Swedish projected data (meters):

# Option 1: Light simplification (keep most detail)
mapshaper modal_k15.geojson -simplify resolution=2 planar keep-shapes -o output01.geojson

# Option 2: Moderate simplification (good balance)
mapshaper modal_k15.geojson -simplify resolution=5 planar keep-shapes -o output02.geojson

# Option 3: Heavy simplification (web-ready)
mapshaper modal_k15.geojson -simplify resolution=10 planar keep-shapes -o output03.geojson

# Option 4: Batch all variants
for res in 2 5 10 20; do
  mapshaper modal_k15.geojson -simplify resolution=$res planar keep-shapes \
    -o "output/modal_k15_res${res}m.geojson"
done
```

