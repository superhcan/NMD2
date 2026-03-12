# Tile-kantproblem vid generalisering och vektorisering

## Rasterbearbetning (gdal_sieve)

`gdal_sieve` ser varje tile isolerat. En yta som korsar en tilekant uppfattas som
**två separata, mindre ytor** – en på varje tile. Om endera delen underskrider
MMU-tröskeln sievas den bort, trots att den kombinerade ytan är tillräckligt stor.

```
Tile A          |  Tile B
  [  klass 41   |   klass 41  ]  ← egentligen EN yta
  400 px        |   200 px
  MMU = 500 px → bägge sievas, men hela ytan är 600 px → borde överleva
```

### Lösningsalternativ (raster)

#### 1. Överlapp/halo (rekommenderas)
Läs varje tile med en buffert (`overlap = max(MMU_STEPS)` pixlar) på alla kanter,
kör sieve på den utvidgade bilden, skriv sedan bara tillbaka den *inre* kärnan.

```python
OVERLAP = 100  # px, >= max MMU

window_with_halo = Window(x_off - OVERLAP, y_off - OVERLAP,
                          w + 2*OVERLAP, h + 2*OVERLAP)
# ... kör sieve ...
inner = sieved[OVERLAP:-OVERLAP, OVERLAP:-OVERLAP]
```

Fungerar om ingen enskild patch är *bredare* än `OVERLAP` pixlar längs kantlinjen.
För NMD med MMU=100 px (1 ha) och tile 2048 px är 100 px halo rimligt.

#### 2. Bearbeta hela rastern i ett svep
Skippa tiles och kör sieve på hela rutan. Minneskrävande (~10 GB+ för NMD
heltäckande), men problemfritt.

#### 3. Dubbelt pass
- Pass 1: bearbeta tiles individuellt
- Pass 2: sy ihop till VRT, kör ett sista sieve-pass

#### 4. Acceptera som känd begränsning
Dokumentera att pixlar inom `max(MMU)` px från en tilekant kan generaliseras
felaktigt. För 2048-px tile och MMU ≤ 100 gäller det ≤ 5 % av arean per tile.

---

## Vektorisering

När man vektoriserar tile-för-tile med `rasterio.features.shapes` skapas
**artificiella kantlinjer** längs tilekanten, även om klassen är identisk på
båda sidor.

```
Tile A                  Tile B
┌───────────────────┐ ┌───────────────────┐
│  klass 41         │ │  klass 41         │
│  → polygon A      │ │  → polygon B      │
└───────────────────┘ └───────────────────┘
                  ↑
         artificiell gräns i GPKG
```

### Lösningsalternativ (vektor)

#### 1. Överlapp i rastersteget
Om rasterna är sömlösa längs kanterna (via halo-metoden ovan) ger `shapes()`
inga artificiella polygongränser.

#### 2. Vektorisera hela rastern via VRT (enklast och korrekt)
Bygg en VRT av alla tile-GeoTIFF:ar och vektorisera i ett svep:

```bash
gdalbuildvrt merged.vrt tiles/NMD2023bas_tile_*.tif
```

```python
with rasterio.open("merged.vrt") as src:
    polys = list(shapes(src.read(1), ...))
```

#### 3. Efterbehandla vektordatan: dissolve + explode
Kör dissolve på klass-attributet per sammanhängande grupp efter att alla tiles
vektoriserats. Kombinationen dissolve + explode slår ihop grannar med samma klass
som delar en tilekant, men behåller separata icke-sammanhängande ytor som egna
features.

```python
import geopandas as gpd

gdf = gpd.read_file("merged.gpkg")

dissolved = (
    gdf.dissolve(by="klass")
       .explode(index_parts=False)
       .reset_index()
)
dissolved.to_file("merged_dissolved.gpkg", driver="GPKG")
```

---

## Rekommendation

Tiles är bra för *rasterbearbetning*, men vektoriseringen bör helst inte följa
samma gränser. Enklast att resonera kring:

- **Raster:** implementera överlapp/halo i bearbetningsskriptet
- **Vektor:** bygg VRT och vektorisera hela datasetet i ett svep
