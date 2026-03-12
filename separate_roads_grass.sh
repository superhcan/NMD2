#!/bin/bash
set -e

BASE_DIR="/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo"
RASTER_DIR="$BASE_DIR/generalized_modal"
OUTPUT_DIR="$BASE_DIR/vectorized"
TMPDIR="/tmp/roads_grass_sep_$$"

echo "Working in: $TMPDIR"
mkdir -p "$TMPDIR"

cleanup() {
    echo "Cleaning up..."
    rm -rf "$TMPDIR"
}
trap cleanup EXIT

cd "$TMPDIR"

# Step 1: Build VRT
echo ""
echo "1. Building VRT of modal_k15 rasters..."
gdalbuildvrt -overwrite modal_k15_all.vrt $RASTER_DIR/*_k15.tif > /dev/null 2>&1
echo "   ✓ Created VRT"

# Step 2: Vectorize all
echo ""
echo "2. Vectorizing all features..."
gdal_polygonize.py modal_k15_all.vrt -f GPKG all_modal_k15.gpkg value markslag > /dev/null 2>&1
echo "   ✓ Vectorized"

# Step 3: Extract only roads (markslag=53) with ogr2ogr
echo ""
echo "3. Extracting roads (markslag=53)..."
ogr2ogr -f GPKG -where "markslag=53" roads_dn53.gpkg all_modal_k15.gpkg value
ROADS_COUNT=$(ogrinfo -so roads_dn53.gpkg | grep "Feature Count:" | awk '{print $NF}')
echo "   ✓ Extracted $ROADS_COUNT road polygons"

# Step 4: Extract non-roads (markslag!=53)
echo ""
echo "4. Extracting non-road features..."
ogr2ogr -f GPKG -where "markslag!=53" other_features.gpkg all_modal_k15.gpkg value
OTHER_COUNT=$(ogrinfo -so other_features.gpkg | grep "Feature Count:" | awk '{print $NF}')
echo "   ✓ Extracted $OTHER_COUNT other polygons"

# Step 5: Create GRASS location with proper projection
echo ""
echo "5. Creating GRASS location (EPSG:3006)..."
rm -rf grassdb
mkdir -p grassdb/project/PERMANENT

# Create PERMANENT mapset with EPSG:3006
grass -c EPSG:3006 grassdb/project --exec g.proj -c epsg=3006 2>&1 | tail -3
echo "   ✓ Created GRASS location"

# Step 6: Import non-road features into GRASS
echo ""
echo "6. Importing non-road features into GRASS..."
grass ./grassdb/project/PERMANENT << EOF
v.in.ogr input=$TMPDIR/other_features.gpkg output=other_features layer=0 --overwrite -q
exit
EOF
echo "   ✓ Imported"

# Step 7: Generalize with topology preservation
echo ""
echo "7. Generalizing with threshold=10m (topology-aware)..."
grass ./grassdb/project/PERMANENT << EOF
v.generalize input=other_features output=other_gen method=douglas threshold=10 -q
exit
EOF
echo "   ✓ Generalized"

# Step 8: Export generalized features
echo ""
echo "8. Exporting generalized features..."
grass ./grassdb/project/PERMANENT << EOF
v.out.ogr input=other_gen output=$TMPDIR/other_gen.gpkg format=GPKG -q
exit
EOF
echo "   ✓ Exported"

# Step 9: Combine roads + generalized with ogr2ogr
echo ""
echo "9. Merging roads + generalized features..."
cp other_gen.gpkg "$OUTPUT_DIR/generalized_modal_k15_roads_preserved.gpkg"
ogr2ogr -append "$OUTPUT_DIR/generalized_modal_k15_roads_preserved.gpkg" roads_dn53.gpkg
echo "   ✓ Merged"

# Step 10: Verify
echo ""
echo "10. Verifying output..."
FINAL_SIZE=$(ls -lh "$OUTPUT_DIR/generalized_modal_k15_roads_preserved.gpkg" | awk '{print $5}')
FINAL_COUNT=$(ogrinfo -so "$OUTPUT_DIR/generalized_modal_k15_roads_preserved.gpkg" | grep "Feature Count:" | awk '{print $NF}')
echo "   File: generalized_modal_k15_roads_preserved.gpkg"
echo "   Size: $FINAL_SIZE"
echo "   Features: $FINAL_COUNT"

echo ""
echo "✓ KLART!"
