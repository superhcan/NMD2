#!/usr/bin/env python3
"""
Extrahera pixlar från 2018-rastern som inte finns i 2023-rastern.
Skapar en ny raster som innehåller endast pixlar som finns i 2018 
men som saknas (är nodata, dvs = 0) i 2023.

De två rastren har olika höjd och förskjuten ursprung, så vi arbetar 
med den gemensamma ytan.
"""

import rasterio
import numpy as np
from rasterio.windows import Window
import rasterio.transform
from pathlib import Path

# Sökvägar
raster_2018 = "/home/hcn/NMD_workspace/NMD2018_basskikt_ogeneraliserad_Sverige_v1_1/nmd2018bas_ogeneraliserad_v1_1.tif"
raster_2023 = "/home/hcn/NMD_workspace/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.tif"
output_path = "/home/hcn/NMD_workspace/difference_2018_minus_2023.tif"

print(f"Läser 2018-raster: {raster_2018}")
print(f"Läser 2023-raster: {raster_2023}")

# Öppna båda rastren
with rasterio.open(raster_2018) as src_2018:
    with rasterio.open(raster_2023) as src_2023:
        # Läs metadata
        profile_2018 = src_2018.profile
        profile_2023 = src_2023.profile
        
        print(f"2018 - Shape: {src_2018.shape}, dtype: {src_2018.dtypes[0]}")
        print(f"2023 - Shape: {src_2023.shape}, dtype: {src_2023.dtypes[0]}")
        print(f"2018 bounds: {src_2018.bounds}")
        print(f"2023 bounds: {src_2023.bounds}")
        
        # Beräkna överlappsregion
        # 2023 är förskjuten 10 pixlar nedåt (y-axeln, motsvarar rad 1)
        # Alltså: 2023 rad 0 motsvarar ungefär 2018 rad 1
        
        rows_2018 = src_2018.shape[0]  # 157992
        rows_2023 = src_2023.shape[0]  # 157991
        cols = src_2018.shape[1]
        
        # Gemensamt område: 2018 rader 1-157991 och 2023 rader 0-157990
        # Det ger båda 157991 rader
        common_rows = 157991
        start_row_2018 = 1
        start_row_2023 = 0
        
        print(f"\nLäser gemensamt område:")
        print(f"2018: rader {start_row_2018}-{start_row_2018 + common_rows - 1} (totalt {common_rows} rader)")
        print(f"2023: rader {start_row_2023}-{start_row_2023 + common_rows - 1} (totalt {common_rows} rader)")
        
        # Läs data med justerad window
        window_2018 = Window(0, start_row_2018, cols, common_rows)
        window_2023 = Window(0, start_row_2023, cols, common_rows)
        
        data_2018 = src_2018.read(1, window=window_2018)
        data_2023 = src_2023.read(1, window=window_2023)
        
        # Nodata-värde är 0 för båda
        NODATA = 0
        
        # Identifiera pixlar
        # Giltiga pixels i 2018: != 0
        # Saknade pixels i 2023: == 0
        mask_2018_valid = data_2018 != NODATA
        mask_2023_nodata = data_2023 == NODATA
        
        # Kombinera: pixlar som är giltiga i 2018 OCH nodata i 2023
        difference_mask = mask_2018_valid & mask_2023_nodata
        
        # Skapa output-array med samma dtype som 2018
        output = np.zeros_like(data_2018, dtype=data_2018.dtype)
        
        # Kopiera värdena från 2018 för de pixlar som uppfyller kriteriet
        output[difference_mask] = data_2018[difference_mask]
        
        # Räkna pixlar
        count_difference = np.count_nonzero(difference_mask)
        count_valid_2018 = np.count_nonzero(mask_2018_valid)
        count_valid_2023 = np.count_nonzero(mask_2023_nodata)
        
        print(f"\nResultat:")
        print(f"Pixlar bara i 2018 (inte i 2023): {count_difference}")
        print(f"Total giltiga pixlar i 2018: {count_valid_2018}")
        print(f"Total nodata-pixlar i 2023: {count_valid_2023}")
        
        # Skapa output-profil baserad på 2018 men anpassad storlek
        output_profile = profile_2018.copy()
        output_profile['height'] = common_rows
        # Justera ursprunget för Y: vi börjar från 2018 rad 1, vilket är 10 pixlar nedåt
        # (en transformenhet nedåt = lägre Y-värde)
        old_transform = output_profile['transform']
        new_transform = rasterio.transform.Affine(
            old_transform.a, old_transform.b, old_transform.c,
            old_transform.d, old_transform.e, old_transform.f + start_row_2018 * abs(old_transform.d)
        )
        output_profile['transform'] = new_transform
        
        # Skriv output
        print(f"\nSkriver output: {output_path}")
        with rasterio.open(output_path, 'w', **output_profile) as dst:
            dst.write(output, 1)
        
        print("Klart!")
