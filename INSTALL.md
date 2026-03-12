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

Generaliseringstest på en tile:

```bash
# Largest-neighbour, 4-konnektivitet (garanterad MMU)
python generalize_test_conn4.py

# Largest-neighbour, 8-konnektivitet
python generalize_test_conn8.py

# Semantisk likhet (ekologiskt motiverade val)
python generalize_test_semantic.py

# Majoritetsfilter (mjuka former, ingen MMU-garanti)
python generalize_test_modal.py
```

Vektorisering av modal k15-resultat:

```bash
python vectorize_modal_k15.py
```

## Utdatamappar

Alla resultat skrivs till `/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/`:

| Mapp | Innehåll |
|------|----------|
| `tiles/` | 1 225 tiles (35×35), 2048×2048 px |
| `generalized_test_conn4/` | Sieve conn4, MMU 2–100 px |
| `generalized_test_conn8/` | Sieve conn8, MMU 2–100 px |
| `generalized_test_semantic/` | Semantisk, MMU 2–100 px |
| `generalized_test_modal/` | Modal filter, k3–k15 |

Varje TIF-fil har en matchande `.qml` för automatisk färgsättning i QGIS.
