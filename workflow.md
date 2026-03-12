# Arbetsflöde: NMD-generalisering och vektorisering

## Steg 1 — Dela upp rastern i tiles
**Skript:** `split_tiles.py`  
**Indata:** `NMD2023bas_v2_0.tif` (hela Sverige)  
**Utdata:** `tiles/NMD2023bas_tile_r{rad:03d}_c{kol:03d}.tif`

- Delar upp källrastern i tiles om 2 048 × 2 048 px
- Varje tile får en kopia av `.qml`-paletten för QGIS
- Komprimering: LZW
- Namnkonvention baseras på rad- och kolumnindex (nollindexerade, nollpaddat till 3 siffror)

> **OBS – tilekanter:** En yta som korsar en tilekant uppfattas av sieve som
> två separata ytor. Se [`tile_boundary_notes.md`](tile_boundary_notes.md) för
> lösningsalternativ (rekommenderat: halo/överlapp).

---

## Steg 2 — Fyll landöar i vatten
**Skript:** `fill_islands.py`  
**Indata:** tile från steg 1 (eller föregående steg)  
**Utdata:** `filled_islands/NMD2023bas_tile_r*_c*_filled.tif`

Sieve-generaliseringen kan aldrig absorbera en liten landyta in i en skyddad
vattenklass, vilket medför att riktiga mikroöar (och klassificeringsfel som
ser ut som öar) överlever MMU-filtret. Det här steget hanterar det specifikt.

- En **ö** definieras som ett sammanhängande landområde vars *samtliga*
  ortogonala grannar tillhör vattenklass `61` eller `62`
- Öar med < **100 px (1 ha)** ersätts med den dominerande vattenklass som
  omger dem
- Delvis omringade ytor (uddar, strandlinje mot land) berörs inte
- Konnektivitet 4 (ortogonalt) för strikt definition av "omringad"

> Körs **före** generaliseringssteget så att sieve inte skapar nya mikroöar
> som missas.

---

## Steg 3 — Generalisering (MMU-baserad, raster)

> **Tilekants-artefakter:** Utan overlap ser sieve/modal/semantic varje tile
> isolerat – en yta som korsar en tilekant delas upp i två separata patches
> som var för sig kan understig MMU och elimineras felaktigt.
>
> **Lösning – halo/överlapp (implementerat i `pipeline_1024_halo.py`):**
> - Varje tile läses med **100 px kant** från granntilesna via en GDAL VRT
> - Generaliseringen körs på den utvidgade ytan (1024 + 200 px)
> - Bara den inre kärnan (1024×1024 px) skrivs till utfilen
> - Behandlingen sker **steg-för-steg** (alla tiles vid MMU=2, sedan alla vid
>   MMU=4 osv.) och en ny VRT byggs efter varje steg, så att halo-pixlarna
>   alltid speglar föregående stegs utdata


Syftet är att ta bort ytor som är för små (underskrider MMU). Pixlar i för
små ytor *byter klass* till närmaste/vanligaste grannklass.

Skyddade klasser (`51`=öppet vatten, `52`=strandlinje, `53`=väg, `54`=bebyggelse, `61`=sjö, `62`=vatten) ändras aldrig.

MMU-steg som testats: `[2, 4, 8, 16, 32, 64, 100]` px  
Pixelstorlek: 10 m → 1 px = 0,01 ha → **100 px = 1 ha** (max testat steg)

Fyra metoder har jämförts parallellt (alla kumulativa, dvs. varje steg
bygger på föregående stegs utdata):

| Skript | Metod | Konnektivitet / fönster |
|--------|-------|------------------------|
| `generalize_test.py` | gdal_sieve (largest neighbour) | 4 |
| `generalize_test_v2.py` | gdal_sieve (largest neighbour) | 4, refaktorerad |
| `generalize_test_conn4.py` | gdal_sieve | 4 — ortogonalt (jämnare kanter) |
| `generalize_test_conn8.py` | gdal_sieve | 8 — diagonala grannar räknas |
| `generalize_test_modal.py` | Majoritetsfiltret (modal filter) | Fönster k=3,5,7,11,13,15 |
| `generalize_test_semantic.py` | Semantisk likhet (minst tematiskt avstånd) | 4 |

### Metodbeskrivningar

**gdal_sieve (conn4/conn8):** Tar bort sammanhängande ytor (patches) som
underskrider tröskel-px. Varje pixel i en bortsiead patch antar värdet av
den dominerande grannpatchen. Konnektivitet 4 = bara ortogonala grannar;
konnektivitet 8 = även diagonala grannar.

**Modal filter:** Ersätter varje pixel med den vanligaste klassen i ett
N×N-fönster (scipy `uniform_filter` per klass). Effektiv MMU ≈ k²/2 px.

**Semantisk:** Eliminerar patches under tröskeln och väljer den angränsande
klassen med lägst semantiskt avstånd (NMD-gruppering), inte nödvändigtvis
den störst grannen.

**Utdatakataloger:**
- `generalized_test/` — generalize_test.py
- `generalized_test_conn4/` — generalize_test_conn4.py
- `generalized_test_conn8/` — generalize_test_conn8.py
- `generalized_test_modal/` — generalize_test_modal.py
- `generalized_test_semantic/` — generalize_test_semantic.py

---

## Steg 3 — Vektorisering
**Skript:** `vectorize_modal_k15.py`  
**Indata:** generaliserat raster (t.ex. modal k=15-output)  
**Utdata:** GeoPackage (`.gpkg`), lager `markslag`, attribut `klass` (int)

- Polygoniserar med `rasterio.features.shapes`
- Bakgrund (klass 0) filtreras bort
- Geometrier valideras med `shapely.make_valid`
- En sammanhängande raster-patch → ett polygon

> **OBS – tilekanter i vektordatan:** Vektorisering tile-för-tile skapar
> artificiella kantlinjer längs tilekanter. Rekommenderat: bygg VRT och
> vektorisera hela datasetet i ett svep, eller kör dissolve+explode i
> efterbehandlingen. Se [`tile_boundary_notes.md`](tile_boundary_notes.md).

---

## Steg 4 — Simplifiering (ej implementerat ännu)
Reducerar antalet noder i polygongränserna utan att ändra vilka ytor som
finns. Görs *efter* vektorisering.

- Metod: Douglas-Peucker (`shapely.simplify`) eller Visvalingam-Whyatt
- Tar bort pixeltrappor längs polygongränser
- Klasskartan påverkas inte — inga ytor försvinner eller byter klass

---

## Ordning

```
1. split_tiles.py               →  tiles/*.tif
2. fill_islands.py              →  filled_islands/*.tif      (öar < 1 ha i vatten fyllda)
3. pipeline_1024_halo.py        →  pipeline_1024_halo/       (steg 1–3 ovan, med halo)
     tiles/                     –  1024 px tiles
     filled/                    –  efter öfyllnad
     generalized_conn4/         –  sieve conn4, MMU 2–100 px
     generalized_conn8/         –  sieve conn8
     generalized_modal/         –  modal k=3–15
     generalized_semantic/      –  semantisk
4. vektorisering                →  *.gpkg                    (råa vektorpolygoner, VRT + shapes)
5. (simplifiering)              →  *.gpkg                    (jämnade polygoner)
```

> `pipeline_1024.py` är en äldre version utan halo – finns kvar för jämförelse.


---

## Testtile
Alla skript är hittills körda på en enskild tile:  
`NMD2023bas_tile_r000_c010.tif` (2 048 × 2 048 px)
