# Metodbeskrivning — NMD2 Pipeline

## Bakgrund

**Nationella Marktäckedata (NMD)** är ett 10 m-upplöst rasterklassificering av Sveriges marktäckning. Originalrastret innehåller detaljklasser (tall, gran, barrblandskog uppdelat på fastmark/våtmark m.m.).

Syftet med denna pipeline är att:

1. **Omklassificera** mark-klasserna till ett hanterbart antal slutklasser (~20 st)
2. **Generalisera** rastret kartografiskt (ta bort brus och isolerade pixlar)
3. **Vektorisera och simplifiera** till ett topologiskt korrekt polygonlager utan luckor eller överlapp
4. **Kombinera** med Lantmäteriets hydrografi för geometriskt korrekt vattenlager

---

## Steg-för-steg-metodöversikt

### Förbehandling — Steg 0–3

**Steg 0 — Tileluppdelning (kan användas för verifikation)**
Originalrastret delas i rutnät-tiles (2048 × 2048 px per tile) utan omklassificering. Tiles används för parallell bearbetning och för att hålla minnesanvändningen hanterbar. Steg 0 producerar tiles med original NMD-koder för QA-granskning.

**Steg 1 — Omklassificering**
En LUT-mappning (`CLASS_REMAP`) tillämpas på varje tile: detaljklasserna i NMD konsolideras till slutklasser. Exempelvis:
- Tallskog på fastmark (111) och på våtmark (121) → slutklass 101
- Granskog på fastmark (112) och på våtmark (122) → slutklass 102
- Alla skogsklasser på fastmark/våtmark slås ihop parvis (8 skogstyper × 2 = 16 → 8 slutklasser 101–108)

Originalklasserna sparas som separat lager per tile för spårbarhet.

**Steg 2 — Extrahera skyddade klasser**
Klasser som ska vektoriseras separat och inte generaliserars (vägar 53, eventuellt byggnader 51, inlandsvatten 61, hav 62) extraheras till ett eget lager per tile. Dessa klasser återinförs i slutsteget via overlay (eventuellet steg 9 för byggnader, steg 11 för vatten).

**Steg 3 — Dissolve vägar i omgivande mark**
Vägpixlar (klass 53) ersätts med omgivande markklass via `scipy.ndimage.distance_transform_edt`. Effekten är att vägar "döljs" inför generalisering.

---

### Rasterfiltrering — Steg 4–5

**Steg 4 — Sjöfilter (valfritt)**
Sjöar och vattendrag under 0,5 ha (50 px vid 10 m) tas bort och ersätts med omgivande mark. Används när mycket små vattenobjekt ska filtreras bort redan på rasterstadiet.

**Steg 5 — Öfilter**
Isolerade land-öar under `MMU_ISLAND` pixlar (standard 25 px = 0,25 ha) som är fullständigt omringade av vatten fylls med den dominerande vattenklasen. Förhindrar att mycket små öar vektoriseras till obetydliga polygoner.

---

### Kartgeneralisering — Steg 6–7

**Steg 6 — Sieve-baserad generalisering med HALO-teknik**

Kärnan i generaliseringsprocessen. GDAL:s `GDALSieveFilter` tillämpas iterativt med ökande MMU-steg (standard: [6, 10, 12, 25, 50] pixlar):

- **Sieve**: Sammanhängande pixelgrupper ("patches") under MMU-gränsen absorberas in i den dominerande grannklassen.
- **Konnektivitet**: `conn4` (upp/ned/vänster/höger) ger konservativare generalisering än `conn8` (alla 8 grannpixlar).
- **Skyddade klasser**: Vatten (61, 62) maskeras ut inför varje sieve-pass och återförs efteråt — vatten ändras aldrig av sieve.
- **Klassspecifikt MMU-max** (`MMU_CLASS_MAX`): Känsliga klasser (t.ex. öppen våtmark 200, buskdominerad mark 42) skyddas när MMU-steget överstiger en tröskel.
- **Kraftledningsskydd** (`MMU_POWERLINE_PATH`): Pixlar under kraftledningsgator skyddas upp till `MMU_POWERLINE_MAX` px — förhindrar att korridorer under kraftledningar silas bort.

**HALO-teknik**: Varje tile bearbetas med en 100 px (= `HALO`) bred överlappsbuffert från granntilar. Denna kant säkerställer att sieve-algoritmen har korrekt granninformation vid tilekanter — annars kan isolerade pixlar längs kanter felbehandlas. Kanten klipps bort efter bearbetning.

Varje MMU-steg är kumulativt: `mmu006` → `mmu010` → `mmu012` → `mmu025` → `mmu050`. Slutresultatet (`_mmu050.tif`) är indata till steg 7.

**Steg 7 — Expand water**

Marken flödar `EXPAND_WATER_PX` (standard 2 px = 20 m) in i vattenytor (klass 61). Detta kompenserar för en systematisk felkälla: GDAL-sieve kan lämna kvar markpixlar längs strandlinjen som borde vara vatten, vilket ger "taggiga" stränder i vektorkartans utseende.

Tekniken: inom 2 px från strandlinjen sätts vattenpixlar till 0 (nodata) — den omgivande markklassen "tar över" dessa pixlar. Det inre vattenomådet (djupare än 2 px) behåller klass 61. Steg 11 lägger sedan Lantmäteriets hydrografi ovanpå, vilket ger korrekt vattengeometri.

---

### Vektorisering — Steg 8–10

**Steg 8 — GRASS-polygonisering och vektorsimplifiering**

Raster → vektor sker i GRASS GIS med full topologihantering. För att hantera hela Sveriges rasterstorlek utan minnesproblem delas Y-axeln i `STRIP_N` horisontella band med `STRIP_OVERLAP_M` meters överlapp. Varje band körs som en oberoende GRASS-session och `STRIP_WORKERS` band körs parallellt.

Per band:
1. `r.external` — läs tiles från steg 7 utan kopiering
2. `r.patch` — sätt ihop tiles till ett band-täckande raster
3. `r.to.vect` — polygonisera (raster → vektor med topologinät)
4. `v.clean` — snap-tolerans 0,5 m för att stänga floating-point-sömmar
5. `v.generalize` — kurvanpassning med `douglas+chaiken`:
   - Douglas-Peucker (5 m tröskel) tar bort kolineära punkter längs pixeltrappor
   - Chaikin corner-cutting (10 m min-avstånd) rundar hörnen mjukt

GRASS bygger ett komplett arc-nät över hela bandet — polygongränser bearbetas som delade kanter, vilket garanterar att ingen lucka eller överlapp uppstår längs polygongränser.

**Steg 9 — Byggnadsoverlay (valfritt)**
Vektoriserar byggnadspolygoner (klass 51) från steg 2 och placerar dem ovanpå steg 8-lagret.

**Steg 10 — Merge strips**
Slår ihop de `STRIP_N` band-GPKGerna till en enda GPKG per generaliseringsvariant med `ogr2ogr -append`.

---

### Overlay och klippning — Steg 11–13

**Steg 11 — Vattenoverlay med LM Hydrografi**

Lantmäteriets hydrografi (polygon-GPKG) klipper in korrekt vattengeometri i marktäckningslagret:

1. Marklagret buffras 0,5 m utåt (`OVERLAY_EXTERNAL_SNAP`) inför difference-operationen. Detta stänger mikroskopiska luckor som kan uppstå längs strandlinjer till följd av generaliseringsartefakter.
2. `difference`-operation: vattenpoly­gonerna klipps ut från marklagret.
3. Vattenpolygonerna läggs in som polygoner med klass 61.

**Steg 12 — Footprint-klippning**
Klipper vektorlagret till rastrets geografiska täckningsyta.

---

## Topologigaranti

Det är ett **kritiskt krav** att outputlagret från steg 8, 10, 11, 12 och 13 alltid är:
- **Täckande** — inga luckor (gaps) i täckningsytan
- **Sammanhängande** — ett enda topologiskt nät
- **Överlappsfritt** — varje pixel tillhör exakt ett polygon-feature

GRASS `v.generalize` bevarar detta krav eftersom det opererar på ett gemensamt arc-nät (delade kanter mellan polygoner förblir delade). Steg 11:s buffertmetod (`OVERLAY_EXTERNAL_SNAP`) garanterar att inget tomrum uppstår längs vattengränser.
