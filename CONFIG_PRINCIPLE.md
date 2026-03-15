# NMD2 Pipeline: Configuration Principle

## 🔴 CRITICAL RULE

**`src/config.py` is the SINGLE SOURCE OF TRUTH for all pipeline configuration.**

All orchestrators and individual steg_*.py scripts must read from config.py, never hardcode configuration.

---

## Configuration Hierarchy

```
src/config.py (PRIMARY SOURCE)
    ↓
run_all_steps.py (reads ENABLE_STEPS, PARENT_TILES)
    ↓
steg_1.py → steg_8.py (read algorithm parameters)
```

---

## What Goes in config.py

### 1. **TILE SELECTION** (Which 4 tiles to process)
```python
PARENT_TILES = [(0, 19), (0, 20), (1, 19), (1, 20)]
```
→ **Change here to process different tiles**

### 2. **STEP ENABLEMENT** (Which steps to run)
```python
ENABLE_STEPS = {
    1: True,   # Set False to skip tilesplitting
    2: True,   # Set False to skip protected class extraction
    3: True,
    4: True,   # Steg 4: GDAL sieve (FIXED, uses gdal_sieve.py)
    5: True,
    6: True,
    7: True,
    8: True,
}
```
→ **Change here to enable/disable steps**

### 3. **ALGORITHM PARAMETERS**
```python
MMU_ISLAND = 100  # Min island size for steg 4 (pixels)
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]  # Steg 5 sieve MMUs
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]  # Steg 5 modal filter sizes
HALO = 100  # Cross-tile boundary overlap (pixels)
```
→ **Change here to tune generalization**

### 4. **PATHS**
```python
SRC = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.tif")
OUT_BASE = Path(os.getenv("OUT_BASE", "default_path"))
```
→ **Override OUT_BASE via environment variable for testing**

---

## Current Configuration (2026-03-15)

| Setting | Value | Note |
|---------|-------|------|
| Tile size | 1024×1024 px | All steg use this |
| Test tiles | r000_c019/020, r001_c019/020 | 2×2 grid |
| Steg 4 method | GDAL gdal_sieve.py | ~2s for 4 tiles |
| Test environ | pipeline_test_4tiles_v8 | 8 files (4 TIF + 4 QML) |

---

## Correct Workflow

### To change tiles:
1. Edit `src/config.py`: `PARENT_TILES = [(0, X), (0, Y), ...]`
2. Run: `export OUT_BASE=.../pipeline_test_4tiles_v8 && python3 run_all_steps.py`

### To skip steps (e.g., skip steg 1, 7, 8):
1. Edit `src/config.py`:
   ```python
   ENABLE_STEPS = {
       1: False,  # Skip tilesplitting
       2: True,
       3: True,
       4: True,
       5: True,
       6: True,
       7: False,  # Skip Mapshaper
       8: False,  # Skip QGIS
   }
   ```
2. Run: `python3 run_all_steps.py`
3. Orchestrator respects config.py automatically

### To test on full Sweden:
1. Edit `src/config.py`: `PARENT_TILES = [(0, 0), (0, 1), ..., (N, N)]` (all tiles)
2. Edit environment: `export OUT_BASE=/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_production`
3. Run: `python3 run_all_steps.py`

---

## What NOT to do

❌ **Don't** hardcode configuration in orchestrators  
❌ **Don't** use `--step` arguments if config.py ENABLE_STEPS exists  
❌ **Don't** modify run_all_steps.py to add new configuration  
❌ **Don't** pass parameters directly to steg_*.py scripts  

✅ **Do** add all configuration to src/config.py  
✅ **Do** include descriptive comments in config.py  
✅ **Do** respect ENABLE_STEPS in orchestrators  
✅ **Do** test configuration changes immediately  

---

## Key Insight

The `src/config.py` file is the interface between users and the pipeline. It should be self-documenting and contain all user-facing settings. Scripts read FROM this file, never override it.

