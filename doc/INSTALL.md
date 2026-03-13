# Installationsanvisningar

## Systemberoenden

Installeras en gång via apt (kräver sudo):

```bash
sudo apt install gdal-bin python3-venv python3-pip
```

| Paket | Innehåller |
|-------|-----------|
| `gdal-bin` | `gdal_sieve.py`, `gdal_polygonize.py` m.fl. |
| `python3-venv` | Stöd för virtuell Python-miljö |
| `python3-pip` | Pakethanteraren pip |

## Python-miljö

Skapa och aktivera en virtuell miljö:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Installera Python-paket:

```bash
pip install -r requirements.txt
```

## Dataunderlag

Lägg NMD2023-datan i `/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/`:

```
NMD2023_basskikt_v2_0/
├── NMD2023bas_v2_0.tif         # Originalrastern (5.8 GB)
├── NMD2023bas_v2_0.qml         # QGIS-färgpalett
└── tiles/                      # Skapas av split_tiles.py
```

## Kör skripten

Dela upp originalrastern i 2048×2048-tiles (körs en gång):

```bash
python split_tiles.py
```

Kör hela rastergeneraliseringspipelinen (5 automatiserade steg):

```bash
python pipeline_1024_halo.py
```

**Pipelinen gör följande:**
- Steg 1: Dela upp i 1024×1024 px sub-tiles
- Steg 2: Extrahera skyddade klasser (51-54, 61-62)
- Steg 3: Extrahera landskapet (utan skyddade klasser)
- Steg 4: Fyll landöar < 1 ha i vatten
- Steg 5: Fyra generaliseringsmetoder parallellt (sieve conn4/8, modal, semantisk)

## Utdatamappar

Alla resultat skrivs till `/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/`:

| Mapp | Innehål |
|------|----------|
| `tiles/` | 1 225 tiles (35×35), 2048×2048 px |
| `protected/` | Skyddade klasser extraherade från original (16 tiles) |
| `landscape/` | Landet (allt utom skyddade) från original (16 tiles) |
| `filled/` | Efter landöfyllnad (16 tiles) |
| `generalized_conn4/` | Sieve conn4, MMU 2–100 px (7 steg × 16 tiles) |
| `generalized_conn8/` | Sieve conn8, MMU 2–100 px |
| `generalized_modal/` | Modal filter, k=3–15 (6 kernels × 16 tiles) |
| `generalized_semantic/` | Semantisk, MMU 2–100 px |

Varje TIF-fil har en matchande `.qml` för automatisk färgsättning i QGIS.
