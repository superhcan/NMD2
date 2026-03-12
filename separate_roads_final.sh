#!/bin/bash
set -e

BASE_DIR="/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo"
RASTER_DIR="$BASE_DIR/generalized_modal"
OUTPUT_DIR="$BASE_DIR/vectorized"
TMPDIR="/tmp/roads_final_$$"
GRASSDATA="$TMPDIR/grassdata"

echo "Working in: $TMPDIR"
mkdir -p "$TMPDIR"

cleanup_all() {
    echo "Cleaning up..."
    rm -rf "$TMPDIR"
}
trap cleanup_all EXIT

cd "$TMPDIR"

# Step 1-2: Build VRT and vectorize
echo ""
echo "1. Building VRT and vectorizing all features..."
gdalbuildvrt -overwrite modal_k15_all.vrt $RASTER_DIR/*_k15.tif > /dev/null 2>&1
gdal_polygonize.py modal_k15_all.vrt -f GPKG all_modal_k15.gpkg value markslag > /dev/null 2>&1
echo "   ✓ Done"

# Step 3-4: Extract roads and non-roads
echo ""
echo "2. Extracting roads (markslag=53) and non-road features..."
ogr2ogr -f GPKG -where "markslag=53" roads.gpkg all_modal_k15.gpkg value 2>/dev/null || true
ogr2ogr -f GPKG -where "markslag!=53" other.gpkg all_modal_k15.gpkg value 2>/dev/null || true
echo "   ✓ Extracted"

# Step 5: Create GRASS location
echo ""
echo "3. Setting up GRASS location..."
rm -rf "$GRASSDATA"
mkdir -p "$GRASSDATA"

grass -c EPSG:3006 "$GRASSDATA/project" --exec echo "Initialized" > /dev/null 2>&1

echo "   ✓ Created"

# Step 6: Generalize with GRASS
echo ""
echo "4. Generalizing non-road features with GRASS..."

grass "$GRASSDATA/project/PERMANENT" --exec v.in.ogr input=$TMPDIR/other.gpkg output=other layer=value --overwrite 2>&1 | grep -i "import\|error" | head -2

grass "$GRASSDATA/project/PERMANENT" --exec v.generalize input=other output=other_gen method=douglas threshold=10 2>&1 | grep -i "general\|error" | head -2

grass "$GRASSDATA/project/PERMANENT" --exec v.out.ogr input=other_gen output=$TMPDIR/other_gen.gpkg format=GPKG 2>&1 | grep -i "export\|error" | head -2

echo "   ✓ Generalized"

# Step 7: Combine
echo ""
echo "5. Merging roads + generalized features..."
cp other_gen.gpkg final_output.gpkg

if [ -f roads.gpkg ]; then
    ogr2ogr -append final_output.gpkg roads.gpkg 2>/dev/null || true
fi

echo "   ✓ Merged"

# Copy to output
cp final_output.gpkg "$OUTPUT_DIR/generalized_modal_k15_roads_preserved.gpkg"

echo ""
echo "✓ KLART!"
FILESIZE=$(ls -lh "$OUTPUT_DIR/generalized_modal_k15_roads_preserved.gpkg" | awk '{print $5}')
echo "   Output: generalized_modal_k15_roads_preserved.gpkg"
echo "   Size: $FILESIZE"
