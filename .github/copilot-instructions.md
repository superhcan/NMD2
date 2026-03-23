# Workspace Instructions

Svara alltid på svenska, oavsett vilket språk användaren skriver på.

Kör alltid `run_all_steps.py` för att exekvera pipelinen. Skapa aldrig egna engångsskript för att köra steg — använd alltid det befintliga skriptet.

## ⚠️ KRITISKT — Steg 8: Topologi MÅSTE bevaras
Dela ALDRIG upp vektorlagret från steg 7 inför Mapshaper-körning. Om filen delas bryts topologin längs snittlinjerna → luckor/överlapp längs sömmar. Mapshaper måste processera hela GPKG:n i ett svep för att kunna bygga ett gemensamt topologinät. Om Mapshaper kraschar av minnesbrist är rätt lösning att öka Node.js heap via `NODE_OPTIONS=--max-old-space-size=16384`, inte att dela upp datan.
