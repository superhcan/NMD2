#!/usr/bin/env python3
"""
Testskript för att verifiera steg 4 logik - små områden av samma klass.
"""

import numpy as np
from scipy import ndimage

# Simulera en liten rasterdata med olika klasser
# 1 = skog, 2 = sjö, 3 = ö
test_data = np.array([
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 2, 2, 2, 1, 1, 1],
    [1, 2, 2, 2, 2, 2, 1, 1],
    [1, 1, 2, 1, 2, 1, 1, 3],  # 3 = små öar
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1],
], dtype=np.uint16)

MMU_ISLAND = 4  # Minimum 4 pixlar för att räknas som ett område
struct_4conn = np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=bool)

print("Original rasterdata:")
print(test_data)
print()

filled_data = test_data.copy()
total_areas_removed = 0

# Bearbeta varje klassificering separat
unique_classes = np.unique(test_data[test_data > 0])
print(f"Unika klasser: {unique_classes}")
print()

for class_val in unique_classes:
    class_mask = (test_data == class_val)
    print(f"\n--- Klass {class_val} ---")
    print("Klassens pixels:")
    print(class_mask.astype(int))
    
    # Labela sammanhängande områden av DENNA klass
    labeled, num_features = ndimage.label(class_mask, structure=struct_4conn)
    print(f"Antal sammanhängande områden: {num_features}")
    
    if num_features == 0:
        continue
    
    # Beräkna storlek på varje komponent
    component_sizes = ndimage.sum(class_mask, labeled, range(num_features + 1))
    print(f"Komponenter och deras storlek: {component_sizes[1:]}")  # Hoppa label 0
    
    # Identifiera små komponenter
    for comp_id in range(1, num_features + 1):
        comp_size = component_sizes[comp_id]
        
        if comp_size < MMU_ISLAND:
            comp_mask = (labeled == comp_id)
            print(f"  → Område {comp_id} är litet ({comp_size}px < {MMU_ISLAND}px), TAR BORT")
            
            # Expandera masken för att hitta grannar
            expanded = ndimage.binary_dilation(comp_mask, structure=struct_4conn, iterations=1)
            neighbor_mask = expanded & ~comp_mask
            
            # Hitta majoritets-värde bland grannar
            if neighbor_mask.any():
                neighbor_vals = test_data[neighbor_mask]
                print(f"    Grann-värden: {neighbor_vals}")
                if len(neighbor_vals) > 0:
                    counts = np.bincount(neighbor_vals.astype(int))
                    replacement_class = np.argmax(counts)
                    print(f"    Majoritets-klass: {replacement_class}")
                    filled_data[comp_mask] = replacement_class
                    total_areas_removed += 1
        else:
            print(f"  ✓ Område {comp_id} är stort ({comp_size}px >= {MMU_ISLAND}px), BEHÅLLS")

print("\n" + "="*50)
print("Resultat efter att små områden tagits bort:")
print(filled_data)
print(f"\nTotalt {total_areas_removed} små områden ersatta")
