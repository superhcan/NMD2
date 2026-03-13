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

## Steg 2 — Extrahera skyddade klasser
**Skript:** `pipeline_1024_halo.py` (funktion `step2_extract_protected`)  
**Indata:** Original-tiles från steg 1  
**Utdata:** `protected/NMD2023bas_tile_r*_c*.tif`

Extraherar ENDAST de skyddade klasserna från original-tiles:
- `51` = Exploaterad mark, byggnad
- `52` = Exploaterad mark, ej byggnad eller väg/järnväg
- `53` = Exploaterad mark, väg/järnväg
- `54` = Exploaterad mark, torvtäkt
- `61` = Sjö och vattendrag
- `62` = Hav

Allt annat sätts till 0 (bakgrund). Dessa klasser **generaliseras aldrig** och
bevaras intakta genom hela pipelinen för senare kombinering med generaliserat
landskap.

---

## Steg 3 — Extrahera landskapet
**Skript:** `pipeline_1024_halo.py` (funktion `step3_extract_landscape`)  
**Indata:** Original-tiles från steg 1  
**Utdata:** `landscape/NMD2023bas_tile_r*_c*.tif`

Extraherar ALLT UTOM de skyddade klasserna från original-tiles:
- Innehåller alla landskapsklasser som KAN generaliseras
- De skyddade klasserna sätts till 0 (bakgrund)

Detta landskap-raster är det som kommer att generaliseras i de följande stegen.

---

## Steg 4 — Fyll landöar i vatten
**Skript:** `pipeline_1024_halo.py` (funktion `step2_fill`)  
**Indata:** Original-tiles från steg 1  
**Utdata:** `filled/NMD2023bas_tile_r*_c*_filled.tif`

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

## Steg 5 — Generalisering (MMU-baserad, raster)

> **Tilekants-artefakter:** Utan overlap ser sieve/modal/semantic varje tile
> isolerat – en yta som korsar en tilekant delas upp i två separata patches
> som var för sig kan understig MMU och elimineras felaktigt.
>
> **Lösning – halo/överlapp (implementerat i `pipeline_1024_halo.py`):**
> - Generaliseringen körs på **landskapet** från steg 3 (skyddade klasser är redan separerade)
> - Varje tile läses med **100 px kant** från granntilesna via en GDAL VRT
> - Generaliseringen körs på den utvidgade ytan (1024 + 200 px)
> - Bara den inre kärnan (1024×1024 px) skrivs till utfilen
> - Behandlingen sker **steg-för-steg** (alla tiles vid MMU=2, sedan alla vid
>   MMU=4 osv.) och en ny VRT byggs efter varje steg, så att halo-pixlarna
>   alltid speglar föregående stegs utdata

Notera: De **skyddade klasserna från steg 2** behålls intakta och kan senare
sammanfogas med de generaliserade landskapen vid vektoriseringen.


Syftet är att ta bort ytor som är för små (underskrider MMU). Pixlar i för
små ytor *byter klass* till närmaste/vanligaste grannklass.

Skyddade klasser (ändras aldrig):
- `51` = Exploaterad mark, byggnad
- `52` = Exploaterad mark, ej byggnad eller väg/järnväg
- `53` = Exploaterad mark, väg/järnväg
- `54` = Exploaterad mark, torvtäkt
- `61` = Sjö och vattendrag
- `62` = Hav

MMU-steg som testats: `[2, 4, 8, 16, 32, 64, 100]` px  
Pixelstorlek: 10 m → 1 px = 0,01 ha → **100 px = 1 ha** (max testat steg)

Fyra metoder har jämförts parallellt (alla kumulativa, dvs. varje steg
bygger på föregående stegs utdata):

Huvudskript: `pipeline_1024_halo.py` (funktioner `step3_sieve_halo`, `step3_modal_halo`, `step3_semantic_halo`)

| Metod | Konnektivitet / fönster | Beskrivning |
|-------|------------------------|-------------|
| Sieve conn4 | 4 — ortogonalt | Largest-neighbour, jämnare kanter |
| Sieve conn8 | 8 — diagonala grannar | Largest-neighbour, snabbare |
| Modal filter | Fönster k=3,5,7,11,13,15 | Majoritetsfilter, mjuka former |
| Semantisk | 4 — ortogonalt | Likhet-baserad (ekologiskt motiverad) |

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

**Utdatakataloger (från `pipeline_1024_halo.py`):**
- `generalized_conn4/` — Sieve conn4, 7 MMU-steg × 16 tiles
- `generalized_conn8/` — Sieve conn8, 7 MMU-steg × 16 tiles
- `generalized_modal/` — Modal filter, 6 kernelstorlekar × 16 tiles
- `generalized_semantic/` — Semantisk, 7 MMU-steg × 16 tiles

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
1. pipeline_1024_halo.py steg 1:  tiles/*.tif                (dela upp original i tiles)
2. pipeline_1024_halo.py steg 2:  protected/*.tif            (extrahera skyddade klasser)
3. pipeline_1024_halo.py steg 3:  landscape/*.tif            (extrahera landskapet)
4. pipeline_1024_halo.py steg 4:  filled/*.tif               (fyll öar i vatten)
5. pipeline_1024_halo.py steg 5a-5d:
     generalized_conn4/           (sieve conn4, MMU 2–100 px)
     generalized_conn8/           (sieve conn8)
     generalized_modal/           (modal k=3–15)
     generalized_semantic/        (semantisk)
6. vectorize_pipeline_1024_halo.py →  vectorized/*.gpkg      (vektorisering)
7. (kombinering + simplifiering)   →  *.gpkg                 (slå ihop skyddade + generaliserade)
```

> `pipeline_1024.py` är en äldre version utan halo – finns kvar för jämförelse.


---

## Pipeline-körning

**Hela rastergeneraliseringspipelinen:**
```bash
python pipeline_1024_halo.py
```

**Därefter vektorisering:**
```bash
python vectorize_pipeline_1024_halo.py
```

Båda steg är fullt automatiserade och körs parallellt där möjligt.
