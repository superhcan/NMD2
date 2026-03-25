"""
generate_reclassify_qml.py — Genererar steg_1_reclassify.qml från original-QML och CLASS_REMAP.

Läser NMD:s originale QML-palett, applicerar CLASS_REMAP och skriver en ny
QML-fil där varje ny slutkod får:
  - Färg från den första ursprungskoden som mappas till den (fastmarksvarianten
    väljs om möjlig, dvs. att koder utan våtmark-suffix prioriteras).
  - Label = den nya kodens namn (hämtat från NMD_LABELS nedan, eller genererat
    från ursprungslabelns kortform).

Output: src/steg_1_reclassify.qml
Kör:    python3 generate_reclassify_qml.py
"""

import re
import sys
from pathlib import Path

# Lägg till src/ i sys.path så att config-modulen kan importeras
# (skriptet körs ibland från projektets rotkatalog, ibland från src/).
sys.path.insert(0, str(Path(__file__).parent))
from config import QML_SRC, CLASS_REMAP

# Utdatafilen hamnar i samma katalog som det här skriptet (src/).
# steg_1_reclassify.py letar efter den med __file__.parent / "steg_1_reclassify.qml".
OUT_QML = Path(__file__).parent / "steg_1_reclassify.qml"

# ──────────────────────────────────────────────────────────────────────────────
# Svenska namn för de nya slutklasserna efter reklassificering
# ──────────────────────────────────────────────────────────────────────────────
NMD_LABELS = {
    3:   "Åkermark",
    21:  "Öppen våtmark på myr",
    22:  "Öppen våtmark ej på myr",
    41:  "Öppen mark utan vegetation",
    51:  "Exploaterad mark, byggnad",
    52:  "Exploaterad mark, ej byggnad/väg",
    53:  "Exploaterad mark, väg/järnväg",
    54:  "Exploaterad mark, torvtäkt",
    61:  "Sjö och vattendrag",
    62:  "Hav",
    101: "Tallskog",
    102: "Granskog",
    103: "Barrblandskog",
    104: "Lövblandad barrskog",
    105: "Triviallövskog",
    106: "Ädellövskog",
    107: "Triviallövskog med ädellövinslag",
    108: "Temporärt ej skog",
    200: "Öppen våtmark",
    421: "Buskdominerad mark",
    422: "Risdominerad mark",
    423: "Gräsdominerad mark",
}

# ──────────────────────────────────────────────────────────────────────────────
# Prioriteringsordning för färgval: välj fastmarksvarianten framför våtmark
# när flera ursprungskoder mappas till samma slutkod.
# Lägre index = högre prioritet.
#
# Bakgrund: CLASS_REMAP slår ihop t.ex. 111 (Tallskog fastmark) och 121
# (Tallskog våtmark) till slutkod 101 (Tallskog). Vi vill att slutkodens färg
# ska komma från fastmarksvarianten (111) eftersom den är mer representativ
# i original-NMD-paletten.
# ──────────────────────────────────────────────────────────────────────────────
COLOR_PRIORITY = [
    # Fastmark (1xx) prioriteras framför våtmark (12x)
    111, 112, 113, 114, 115, 116, 117, 118,
    # Sedan myrar/våtmarker i fallback-ordning
    211, 221, 200,
    # Fjällklasser
    43, 23, 230,
    # Öppen mark
    411, 412, 413,
    4211, 4221, 4231,
    # Dessa har bara en källa, ordningen spelar ingen roll
    3, 51, 52, 53, 54, 61, 62,
]


def parse_palette(qml_path: Path) -> dict[int, dict]:
    """
    Läser en QGIS QML-palett och returnerar dess poster som en dict.

    Returnerar: {pixelvärde: {"color": "#rrggbb", "label": "...", "alpha": "255"}}

    QML-formatet innehåller rader på formen:
       <paletteEntry alpha="255" value="111" label="Tallskog på fastmark" color="#6d8b05"/>
    Regex-mönstret extraherar alla fyra attributen i en svep.
    """
    text = qml_path.read_text(encoding="utf-8")
    # Matchar alla paletteEntry-taggar oavsett attributordning (QGIS garanterar
    # dock den ordning vi har i mönstret).
    pattern = re.compile(
        r'<paletteEntry\s+alpha="(\d+)"\s+value="(\d+)"\s+label="([^"]*)"\s+color="([^"]*)"'
    )
    entries = {}
    for m in pattern.finditer(text):
        alpha, value, label, color = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        entries[value] = {"color": color, "label": label, "alpha": alpha}
    return entries


def build_new_palette(orig: dict[int, dict]) -> dict[int, dict]:
    """
    Bygger ny palett {new_value: {color, label}} baserat på CLASS_REMAP.

    Algoritm:
    1. Gruppera alla poster i CLASS_REMAP efter slutkod (new_code).
    2. För varje grupp: välj den ursprungskod (old_code) som har lägst index
       i COLOR_PRIORITY. Om ingen kod finns i listan används lägst numeriskt
       värde som tiebreak (deterministiskt, oberoende av dict-iteration).
    3. Slå upp den valda kodens färg i orig-paletten. Om koden saknas i
       orig (t.ex. för koder som inte finns i original-NMD) används grå.
    4. Sätt label till det svenska namn som definieras i NMD_LABELS, med
       slutkoden som prefix (t.ex. "101 Tallskog").
    """
    # Steg 1: Gruppera old_code → new_code som (prioritet, old_code)-tupler
    groups: dict[int, list] = {}
    for old, new in CLASS_REMAP.items():
        if new is None:
            continue
        if new not in groups:
            groups[new] = []
        # Lägre index i COLOR_PRIORITY = bättre prioritet; okänd kod = 9999
        prio = COLOR_PRIORITY.index(old) if old in COLOR_PRIORITY else 9999
        groups[new].append((prio, old))

    new_palette = {}
    for new_code, sources in groups.items():
        # Steg 2: sortera så att bäst prioritet hamnar först
        sources.sort()
        best_old = sources[0][1]

        # Steg 3: hämta färg från originalpallen
        if best_old in orig:
            color = orig[best_old]["color"]
            alpha = orig[best_old]["alpha"]
        else:
            # Ursprungskoden saknas i original-QML → grå fallback
            color = "#808080"
            alpha = "255"

        # Steg 4: sätt label med nummerprefixet som QGIS visar i legendpanelen
        label = NMD_LABELS.get(new_code, f"{new_code}")
        new_palette[new_code] = {"color": color, "label": f"{new_code} {label}", "alpha": alpha}

    return new_palette


def write_qml(new_palette: dict[int, dict], orig_path: Path, out_path: Path) -> None:
    """
    Skriver ny QML med samma XML-struktur som originalet men med ny palett.

    Strategi: läs hela original-QML som text och ersätt bara
    <colorPalette>...</colorPalette>-blocket med de nya posterna.
    Allt annat (renderingsinställningar, CRS, metadata) ärvs oförändrat
    från originalet, vilket säkerställer kompatibilitet med QGIS.
    """
    orig_text = orig_path.read_text(encoding="utf-8")

    # Bygg nya paletteEntry-rader, sorterade på pixelvärde (numeriskt stigande)
    # så att QGIS-legenden visas i konsekvent ordning.
    entries_xml = "\n".join(
        f'        <paletteEntry alpha="{v["alpha"]}" value="{code}" '
        f'label="{v["label"]}" color="{v["color"]}"/>'
        for code, v in sorted(new_palette.items())
    )

    # re.DOTALL krävs för att . ska matcha radbrytningar inuti blocket.
    new_text = re.sub(
        r"<colorPalette>.*?</colorPalette>",
        f"<colorPalette>\n{entries_xml}\n      </colorPalette>",
        orig_text,
        flags=re.DOTALL,
    )

    out_path.write_text(new_text, encoding="utf-8")
    print(f"Skriven: {out_path}")
    print(f"Antal poster i ny palett: {len(new_palette)}")


def main():
    print(f"Läser original-QML: {QML_SRC}")
    orig = parse_palette(QML_SRC)
    print(f"  → {len(orig)} originalposter inlästa")

    # Bygg ny palett utifrån CLASS_REMAP och prioritetsordning
    new_palette = build_new_palette(orig)
    print(f"  → {len(new_palette)} nya poster efter CLASS_REMAP")

    # Kontrollera att alla nya slutkoder kan hitta en källfärg i originalet.
    # Koder som saknas i orig-paletten får grå fallback (#808080) och bör
    # läggas till i QML_SRC eller hanteras manuellt.
    missing = [
        new for new in new_palette
        if not any(
            old in orig
            for old, n in CLASS_REMAP.items()
            if n == new
        )
    ]
    if missing:
        print(f"Saknar källfärg för slutkoder: {missing} (grå används)")

    write_qml(new_palette, QML_SRC, OUT_QML)


if __name__ == "__main__":
    main()
