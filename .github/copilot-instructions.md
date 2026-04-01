# Workspace Instructions

Svara alltid på svenska, oavsett vilket språk användaren skriver på.

Kör alltid `run_all_steps.py` för att exekvera pipelinen. Skapa aldrig egna engångsskript för att köra steg — använd alltid det befintliga skriptet.

## ⚠️ KRITISKT — Topologisk sammanhängighet MÅSTE alltid garanteras
Outputlagret från varje steg MÅSTE vara ett täckande, samanhängande polygonlager utan luckor (gaps) och utan överlapp (overlaps). Varje pixel i täckningsytan ska tillhöra exakt ett polygon-feature. Detta gäller för hela pipeline-kedjan — steg 8, steg 10 och alla efterföljande steg.

**Konsekvens för steg 10 (overlay extern vektorfil):**
- `gpd.overlay(how='difference')` och `Shapely.difference()` opererar polygon-för-polygon utan gemensamt topologinät → kan ge mikroskopiska luckor längs vattengränser (generaliseringsartefakter från steg 8).
- GRASS `v.overlay op=not` bygger ett korrekt arc-nät men ger 909+ "areas without category" = luckor när markpolygonerna inte täcker exakt mot vattengränserna.
- Rätt lösning: markpolygonerna måste täcka hela ytan **innan** vatten läggs ovanpå. Buffra marklagret lätt utåt (0.5 m) inför overlay, så att alla generaliseringsluckor stängs, och klipp sedan bort vatten ovanpå det buffrade lagret.

## ⚠️ KRITISKT — Steg 8: Topologi MÅSTE bevaras
Dela ALDRIG upp vektorlagret från steg 7 inför Mapshaper-körning. Om filen delas bryts topologin längs snittlinjerna → luckor/överlapp längs sömmar. Mapshaper måste processera hela GPKG:n i ett svep för att kunna bygga ett gemensamt topologinät. Om Mapshaper kraschar av minnesbrist är rätt lösning att öka Node.js heap via `NODE_OPTIONS=--max-old-space-size=16384`, inte att dela upp datan.
