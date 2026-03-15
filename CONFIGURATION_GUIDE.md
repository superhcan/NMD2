# Konfigurationsguide - NMD2 Pipeline

## Översikt
Alla inställningar för pipelinen kan konfigureras i `src/config.py`. Du behöver inte ändra något i steg-filerna.

---

## 1. Generaliseringsmetoder

### Vilka metoder ska köras?
Redigera i `src/config.py`:

```python
GENERALIZATION_METHODS = {"conn4", "conn8", "modal"}
```

**Tillgängliga metoder:**
| Metod | Beskrivning | Snabbhet |
|-------|-------------|----------|
| `conn4` | Sieve (4-connected) | Snabb ✓ |
| `conn8` | Sieve (8-connected) | Snabb ✓ |
| `modal` | Modal filter | Medium |
| `semantic` | Semantisk generalisering | Långsam |

**Exempel:**
```python
# Bara snabb test
GENERALIZATION_METHODS = {"modal"}

# Standard produktionsval
GENERALIZATION_METHODS = {"conn4", "modal"}

# Alla metoder för jämförelse
GENERALIZATION_METHODS = {"conn4", "conn8", "modal", "semantic"}
```

---

## 2. MMU-steg för Sieve (Steg 6a & 6b)

**VIKTIGT: MMU = Minimum Mapping Unit. Större värde = mer generalisering (mindre detalj bevarad).**

### Så Fungerar Det - Teknisk Förklaring

**Siev-algoritmen** (conn4 och conn8) identifierar samanhängande pixelgrupper och klassificerar dem efter storlek:

1. **Identifiera pixelgrupper**: Hitta alla sammanhängande områden av samma klassifikation
   - conn4: Endast horisontala & vertikala grannar räknas
   - conn8: Även diagonala grannar räknas
   
2. **Mät gruppstorlek**: Räkna antal pixlar i varje grupp

3. **Jämför med MMU**: 
   - Om gruppstorlek < MMU → **Pixlarna ersätts med den omgivande klassens värde** (sieveras ut)
   - Om gruppstorlek ≥ MMU → **Pixlorna behålls oförändrade**

#### Konkret Exempel

Originaldata (5×5 pixlar, klassifikation 11):
```
Omgivande klass = 1 (vatten)
Målklass = 11 (skog)

Original:
  1 1 1 1 1
  1 11 11 1 1
  1 11 1 1 1
  1 1 1 1 1
  1 1 1 1 1

Grupp av klass 11: 3 pixlar (markerad med *)
  1  1  1  1  1
  1 11*11* 1  1
  1 11*  1  1
  1  1  1  1  1
```

**Med MMU=2**: Gruppen (3 px) ≥ 2 → **Behålls**
```
  1 1 1 1 1
  1 11 11 1 1
  1 11 1 1 1
  1 1 1 1 1
  1 1 1 1 1
```

**Med MMU=4**: Gruppen (3 px) < 4 → **Alla 11:or ersätts med omgivningen (1)**
```
  1 1 1 1 1
  1  1  1 1 1
  1  1 1 1 1
  1 1 1 1 1
  1 1 1 1 1
```

**Med MMU=8**: Gruppen (3 px) < 8 → **Samma resultat, alla 11:or ersätts**
```
  1 1 1 1 1
  1  1  1 1 1
  1  1 1 1 1
  1 1 1 1 1
  1 1 1 1 1
```

### Allmän Förklaring

MMU (Minimum Mapping Unit) i pixlar definierar den minsta pixelgruppstorlek som ska bevaras. Alla pixelgrupper mindre än MMU-värdet "sållas bort" (sieveras ut):

```
MMU=2   = Behåll pixelgrupper >= 2 px
          → Nästan original, mycket små detaljer kvar
          → Minimal generalisering

MMU=16  = Behåll pixelgrupper >= 16 px
          → Medium generalisering
          → Märkbar förenkling visas

MMU=64  = Behåll pixelgrupper >= 64 px
          → Stark generalisering
          → Många små omraden försvinner
```

### Konfigurera
```python
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
```

### Exempel

**Snabb test** (3 steg = ~40% snabbare):
```python
MMU_STEPS = [2, 8, 32]
```
- Färre utgångspunkter men representativ täckning

**Standard** (7 steg, rekommenderat):
```python
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
```
- Bra balans mellan körtid och resultatkvalitet

**Detaljerad analys** (9 steg, långsamt):
```python
MMU_STEPS = [1, 2, 4, 8, 16, 32, 64, 100, 128]
```
- Många nivåer för detaljerad analys av effekt

### Effekt på Filstorlek & Detalj

| MMU | Filstorlek (ungefär) | Detalj | Användning |
|-----|---|---|---|
| 2 | 100% av original | Nästan original | Presentationskvalitet |
| 4 | 95-98% av original | Nästan original | Webbaserade kartor |
| 8 | 85-95% av original | Bra detalj kvar | Standard visualisering |
| 16 | 75-85% av original | Medium detalj | Överblick med viss detalj |
| 32 | 50-70% av original | Reducerad detalj | Generell överblick |
| 64 | 30-50% av original | Mycket reducerad | Grov kartöversikt |
| 100 | 15-30% av original | Minimal detalj | Extrem förenkling |

### Praktiska Exempel

**För kartpresentationer** (behål mycket detalj):
```python
MMU_STEPS = [2, 4, 8]
```
- Behål nästan original upplösning med endast bort-sievning av brus

**För webkarta/överblick** (balanserad förenkling):
```python
MMU_STEPS = [8, 16, 32]
```
- Medium generalisering lätt att ta åt sig

**För grov kartöversikt** (aggressiv förenkling):
```python
MMU_STEPS = [32, 64, 100]
```
- Bara större strukturer kvar, mycket små omraden borta

### Tips
- Första värdet bör oftast vara 2-4 px (annars för liten förenkling)
- Sista värdet bör matcha eller överstiga `HALO` för att undvika edge-artefakter
- Större steg mellan värden = snabbare körtid men färre utgångspunkter
- Fler steg = längre körtid men bättre för jämförelse

---

## 3. Kernel-storlekar för Modal Filter (Steg 6c)

**VIKTIGT: K-värde = fönsterstorlek för "majority voting". Större K = mer generalisering (mindre detalj bevarad).**

### Så Fungerar Det - Teknisk Förklaring

**Modal filter** använder "majority voting" för att ersätta pixlar:

1. **Skapa ett K×K fönster** omkring varje pixel
2. **Räkna frekvensen** av varje värde/klass inom fönstret
3. **Ersätt pixeln** med det värde som förekommer MEST (vanligaste värdet)
4. **Flytta fönstret** till nästa pixel och upprepa

#### Konkret Exempel - Kernel k=3

Original rasterdata (7×7 pixlar, klassifikation 1-3):
```
Original:
  1 1 2 2 2 1 1
  1 2 2 2 3 1 1
  1 2 2 3 3 1 1
  1 2 3 3 3 1 1
  1 2 3 3 1 1 1
  1 1 3 1 1 1 1
  1 1 1 1 1 1 1
```

**Bearbeta pixel (2,2) med k=3** (3×3 fönster):
```
Fönster omkring pixel (2,2):
  1 2 2
  2 2 2  ← Mittenpixeln som ska ersättas
  2 2 3

Frekvensräkning:
  Värde 1: förekommer 1 gång (1/9)
  Värde 2: förekommer 6 gånger (6/9) ← VANLIGASTE
  Värde 3: förekommer 2 gånger (2/9)

Ersätt med 2 (det vanligaste värdet)
Resultat: pixel blir 2
```

**Bearbeta pixel (3,5) med k=3** (3×3 fönster):
```
Fönster omkring pixel (3,5):
  2 3 1
  3 1 1  ← Mittenpixeln som ska ersättas (värdeer 1)
  3 1 1

Frekvensräkning:
  Värde 1: förekommer 5 gånger (5/9) ← VANLIGASTE
  Värde 2: förekommer 1 gång (1/9)
  Värde 3: förekommer 3 gånger (3/9)

Ersätt med 1 (det vanligaste värdet)
Resultat: pixel blir 1
```

**Efter k=3 modal filter (hela bilden)**:
```
Resultat efter 3×3 modal filter:
  1 1 2 2 2 1 1
  1 2 2 2 2 1 1   ← Mindre variabilitet
  1 2 2 2 3 1 1   ← Småpixlar utjämnade
  1 2 2 3 3 1 1
  1 2 2 3 1 1 1   ← Smågrupper försvinner
  1 1 2 1 1 1 1
  1 1 1 1 1 1 1
```

#### Större Kernel k=5

Med ett större fönster blir effekten starkare:
```
k=5 = 5×5 fönster → större område granskas
      → Mer "röstning" från omgivningen
      → Fler små detaljer försvinner
      → Mer enfärgade områden
```

Samma pixel (3,5) med k=5 (5×5 fönster):
```
Större fönster innehåller mer av originaldata
→ Ännu större chans att omgivningen "överröstar" originalvärdet
→ Effekten bli ännu starkare
```

### Allmän Förklaring

```
k=3   = 3×3 pixel fönster
        → Nästan original, bara små brus tas bort
        → Minimal generalisering

k=7   = 7×7 pixel fönster
        → Medium generalisering
        → Märkbar förenkling visas

k=15  = 15×15 pixel fönster
        → Stark generalisering
        → Många små omraden försvinner
```

### Konfigurera
```python
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
```

### Exempel

**Snabb test** (3 steg = ~50% snabbare):
```python
KERNEL_SIZES = [3, 7, 13]
```
- Representativ täckning från liten till stor kernel

**Standard** (6 steg, rekommenderat):
```python
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
```
- Bra täckning från fin till grov generalisering

**Detaljerad analys** (9 steg, långsamt):
```python
KERNEL_SIZES = [3, 5, 7, 9, 11, 13, 15, 17, 19]
```
- Många nivåer för detaljerad analys

### Effekt på Filstorlek & Detalj

| Kernel | Fönster | Filstorlek (ungefär) | Detalj | Användning |
|--------|---------|---|---|---|
| k=3 | 3×3 | 100% av original | Nästan original | Brus-borttagning |
| k=5 | 5×5 | 95-98% av original | Nästan original | Presentationskvalitet |
| k=7 | 7×7 | 85-95% av original | Bra detalj kvar | Webbaserade kartor |
| k=9 | 9×9 | 75-85% av original | Medium detalj | Standard visualisering |
| k=11 | 11×11 | 65-75% av original | Reducerad detalj | Överblick |
| k=13 | 13×13 | 50-65% av original | Mycket reducerad | Grov kartöversikt |
| k=15 | 15×15 | 40-55% av original | Minimal detalj | Extrem förenkling |

### Praktiska Exempel

**För kartpresentationer** (behål mycket detalj):
```python
KERNEL_SIZES = [3, 5, 7]
```
- Liten till medium generalisering behål detaljerna

**För webkarta/överblick** (balanserad förenkling):
```python
KERNEL_SIZES = [5, 7, 11]
```
- Bra balans mellan förenkling och bevarad detalj

**För grov kartöversikt** (aggressiv förenkling):
```python
KERNEL_SIZES = [11, 13, 15]
```
- Stark generalisering, bara större strukturer kvar

### Tips
- ODD värden (3, 5, 7, 9, ...) är standard för symmetrisk pixel-fönstring
- Börja med k=3 eller k=5 för att behål mestadels original detalj
- Kernel måste passa helt inom tile + HALO område
- Begränsning: k ≤ (2×HALO+1) för att undvika edge-artefakter
- Större kernel = längre körtid (ungefär kvadratisk komplexitet)

---

## 4. Mapshaper Förenkling - Toleranser (Steg 8)

**VIKTIGT: Denna parameter konfigurerar hur många vertices som SKA BEHÅLLAS, inte hur många som tas bort!**

### Så Fungerar Det - Teknisk Förklaring

**Mapshaper simplifikation** använder Weighted Visvalingam-Whyatt algoritmen (default) för att identifiera och ta bort "removable vertices":

#### Algoritmen - Steg för Steg

1. **Klassifiera vertices**: Markera vilka vertices som kan tas bort utan väsentlig geometriförändring
   - Vertices på raka stretchor: kan tas bort utan problem
   - Vertices vid skarpa vinklar: viktiga, bör bevaras
   - Vertices vid små utskjutningar: kandidater för borttagning

2. **Beräkna viktning**: För varje vertex beräknas en "viktighet"
   - Stora vinklar (< 45°): höga vikter (viktiga)
   - Små vinklar (> 135°): låga vikter (kan tas bort)
   - Längden på kanterna påverkar också viktningen

3. **Rangordna**: Sortera vertices efter viktning (minst viktiga först)

4. **Behål X%**: 
   - p90: Behål bara de 90% viktigaste vertices → ta bort de 10% minst viktiga
   - p50: Behål bara de 50% viktigaste vertices → ta bort de 50% minst viktiga  
   - p15: Behål bara de 15% viktigaste vertices → ta bort de 85% minst viktiga

#### Konkret Exempel

Original polygon (15 vertices):
```
Polygon form: En ojämn kustlinje med många små detaljer

Original:
    ●─────●─────●
   /       \     \
  ●         ●─●  ●
  │      ●     ●  
  ●     / \     ●
   \   ●   ●   /
    ●─●─────●─●

Vertices: 15 st
Edges: 15 st
```

**Med p90 (behål 90% av vertices)**:
```
Beräkna viktning för alla 15 vertices:
  - 9 vertices identifieras som "removable" (små utskjutningar)
  - 6 vertices identifieras som "kritiska" (stora vinklar)

Ranking av removable vertices (minst viktiga först):
  1. Liten pixel-utskjutning → väg-vertex
  2. Små vinklar på båda sidor → väg-vertex
  3. ... (fortsätt för alla 9)
  
Behål 90%: 15 × 0.90 = 13.5 ≈ 13 vertices
  → Ta bort de 2 minst viktiga vertices (99% och 98% viktiga)

Resultat: 13 vertices (endast små utskjutningar borta)
```

**Med p50 (behål 50% av vertices)**:
```
Behål 50%: 15 × 0.50 = 7.5 ≈ 7-8 vertices
  → Behål bara de viktigaste vertices
  → Ta bort många små detaljer

Resultat: 7-8 vertices (många små detaljer borta, stort fokus på stora strukturer)
```

**Med p15 (behål 15% av vertices)**:
```
Behål 15%: 15 × 0.15 = 2.25 ≈ 2-3 vertices
  → Bara de absolut viktigaste vertices bevaras
  → Extremt förenklad geometri

Resultat: 2-3 vertices (nästan bara raka linjer, all detalj försvinner)
```

#### Visuell Jämföring

```
Original (p100):  ～～～～～～～～～～ (många smala svängningar)
p90:              ─～─～─～─～─~~~── (lite förenklat)
p75:              ───～─～────~~──── (märkbar försenkling)
p50:              ─────────────────  (helt utplånad, stora drag)
p15:              ╱╲─╲╱╲───╱╲──╱╲  (extrem förenkling)
```

### Allmän Förklaring

Mapshaper behåller ett specifikt **percentage av "removable vertices"** (vertices som kan tas bort utan att ändra geometrin väsentligt):

```
p90 = Behåll 90% av removable vertices
      → Nästan original geometri
      → Minimal förenkling
      → Stor filstorlek
      → Många detaljer bevarade

p50 = Behåll 50% av removable vertices  
      → Medium förenkling
      → Medel filstorlek
      → Bra balans mellan förenkling och detalj

p15 = Behåll 15% av removable vertices
      → Aggressiv förenkling
      → Liten filstorlek
      → Mest detaljer försvinner
```

### Konfigurera
```python
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]
```

### Exempel

**Snabb test** (färre nivåer):
```python
SIMPLIFICATION_TOLERANCES = [75, 25]
```
Bara två nivåer för snabb feedback

**Standard** (rekommenderat):
```python
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]
```
5 nivåer som täcker spektrumet från minimal till aggressiv

**Detaljerad analys**:
```python
SIMPLIFICATION_TOLERANCES = [95, 85, 75, 65, 50, 35, 20, 10, 5]
```
Många nivåer för detaljerad jämförelse

### Effekt på Filstorlek

| Tolerance | Filstorlek (ungefär) | Detalj | Användning |
|-----------|---|---|---|
| p95 | 105-110% av original | Nästan original | Kartpresentationer |
| p90 | 95-100% av original | Nästan original | Webbaserade kartor |
| p75 | 70-80% av original | Bra detalj kvar | Mobila appar |
| p50 | 50-60% av original | Medium detalj | Webb-kartor |
| p25 | 20-30% av original | Reducerad detalj | Överblickskarta |
| p15 | 10-20% av original | Mycket reducerad | Liten filstorlek |
| p5 | 5-10% av original | Minimal detail | Extrem förenkling |

### Praktiska Tips

**För presentationskvalitet**: Använd `p90` eller `p75`
```python
SIMPLIFICATION_TOLERANCES = [90, 75, 50]
```

**För webbkarta**: Använd `p50` eller `p25`
```python
SIMPLIFICATION_TOLERANCES = [50, 25]
```

**För lätt data**: Använd `p15` eller lägre
```python
SIMPLIFICATION_TOLERANCES = [25, 15, 5]
```

### Exempel: Jämförande Skalning

Med en original GeoPackage på **50 MB**:
```
p95  → ~52 MB   (nästan ingen förenkling)
p90  → ~50 MB   (minimal förenkling)
p75  → ~38 MB   (30% förenkling)
p50  → ~28 MB   (44% förenkling)
p25  → ~12 MB   (76% förenkling)
p15  →  ~8 MB   (84% förenkling)
p5   →  ~4 MB   (92% förenkling - extrem!)
```

---

## 5. Praktiska Konfigurationsscenarier

### Scenario A: Snabb Prototyping
Fokus: Få resultat snabbt

```python
GENERALIZATION_METHODS = {"modal"}
MMU_STEPS = [2, 4, 8]
KERNEL_SIZES = [3, 7, 13]
SIMPLIFICATION_TOLERANCES = [75, 25]
```
**Körtid för 4 tiles**: ~10-15 minuter

### Scenario B: Standardkörning
Fokus: Bra balans mellan tid och resultat

```python
GENERALIZATION_METHODS = {"conn4", "modal"}
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]
```
**Körtid för 4 tiles**: ~2 minuter

### Scenario C: Fullständig Analys
Fokus: Jämföra alla metoder och parametrar

```python
GENERALIZATION_METHODS = {"conn4", "conn8", "modal", "semantic"}
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15, 5]
```
**Körtid för 4 tiles**: 60+ minuter
**QGIS-projekt**: 100+ MB

### Scenario D: Production (Sverige)
Fokus: Snabbhet på stort dataset

```python
GENERALIZATION_METHODS = {"modal"}
MMU_STEPS = [8, 16, 32, 64, 100]        # Hoppa över små värden
KERNEL_SIZES = [7, 11, 15]              # Bara 3 kernelstorlekar
SIMPLIFICATION_TOLERANCES = [50, 25]
```
**Körtid för 1 tile**: ~2-3 minuter

---

## 6. Andra Viktiga Parametrar

### HALO - Överlappningsbredd
```python
HALO = 100  # pixels
```
- Måste vara >= max(MMU_STEPS)
- Ingen anledning att ändra detta normalt

### PROTECTED - Skyddade Klasser
```python
PROTECTED = {51, 52, 53, 54, 61, 62}
```
Klasser som inte ändras under generalisering (vägar, byggnader, vatten)

### ENABLE_STEPS - Vilka steg ska köras?
```python
ENABLE_STEPS = {
    1: False,   # Tilesplitting (hoppa över - tiles finns redan)
    2: True,    # Extrahera skyddade klasser
    3: True,    # Landskapsbild
    4: True,    # Fyllda sjöar
    5: True,    # Fylld öar
    6: True,    # Generalisering
    7: True,    # Vektorisering
    8: True,    # Mapshaper
    9: True,    # QGIS-projekt
}
```

---

## 7. Hur Konfigurationen Propageras

```
config.py: GENERALIZATION_METHODS = {"conn4", "modal"}
              ↓
Steg 6: Läser config, kör endast conn4 och modal
              ↓
Steg 7: Läser config, vektoriserar endast dessa två
              ↓
Steg 8: Söker dynamisk efter .gpkg-filer från steg 7, förenklar
              ↓
Steg 9: Bygger QGIS-projekt med alla tillgängliga lager
```

**Du behöver bara ändra config.py** - de andra stegen adapterar automatiskt!

---

## 8. Förekommande Praxis

### För Snabb Feedback
- Använd Scenario A (Snabb Prototyping)
- Test ofta med nya parametrar

### För Produktionsmiljö (Full Sverige)
- Använd Scenario D
- Batch-kör över flera tiles
- Spara konfigurationen i version control

### För Metodjämförelse
- Använd Scenario C
- Analysera resultat innan skalning

---

## 9. Kontroll av Din Konfiguration

Kör steg 6 och se i loggarna:
```
11:35:35 [INFO  ] Aktiva generaliseringsmetoder: ['conn4', 'modal']
11:35:35 [INFO  ] MMU-steg  : [2, 4, 8, 16, 32, 64, 100] px
11:35:35 [INFO  ] Kernelstorlekar (modal): [3, 5, 7, 11, 13, 15]
```

Om du inte ser dina värden, kontrollera att du sparade `config.py`!
