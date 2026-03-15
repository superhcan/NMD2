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

MMU (Minimum Mapping Unit) i pixlar för sieve-filtren.

### Konfigurera
```python
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
```

### Exempel

**Snabb test** (färre steg = snabbare):
```python
MMU_STEPS = [2, 4, 8]
```
- Dock: Färre utgångspunkter för jämförelse

**Standard** (bra balans):
```python
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
```
- Rekommenderat för fullt resultat

**Detaljerad analys** (många steg):
```python
MMU_STEPS = [1, 2, 4, 8, 16, 32, 64, 100]
```
- Längre körtid men finner optimalt värde

### Tips
- Större MMU-värden = mer generalisering (mindre detalj)
- Första värdet bör oftast vara 2-4 px
- Max-värdet bör matcha eller överstiga `HALO`

---

## 3. Kernel-storlekar för Modal Filter (Steg 6c)

Kernel-storlek k för modal filter. Större k = större generalisering.

### Konfigurera
```python
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
```

### Exempel

**Snabb test**:
```python
KERNEL_SIZES = [3, 7, 13]
```
- 3 nivåer istället för 6 → ~50% snabbare

**Standard**:
```python
KERNEL_SIZES = [3, 5, 7, 11, 13, 15]
```
- Bra täckning från fin till grov

**Detaljerad**:
```python
KERNEL_SIZES = [3, 5, 7, 9, 11, 13, 15, 17, 19]
```
- Många nivåer för att analysera effekt

### Effekt
| Kernel | Effekt |
|--------|--------|
| k=3 | Mycket liten - nästan ingen skillnad |
| k=5 | Liten förenkling |
| k=7-11 | Medium förenkling |
| k=13-15 | Stark förenkling |

---

## 4. Mapshaper Förenkling - Toleranser (Steg 8)

Toleransnivåer för vertex-förenkling (procentuell).
- **Höga värden** (90%, 75%) = sparar många vertices = mindre förenkling
- **Låga värden** (15%, 25%) = tar bort många vertices = större förenkling

### Konfigurera
```python
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]
```

### Exempel

**Snabb test** (färre nivåer):
```python
SIMPLIFICATION_TOLERANCES = [75, 50, 25]
```

**Standard**:
```python
SIMPLIFICATION_TOLERANCES = [90, 75, 50, 25, 15]
```
- Bra täckning från minimal till aggressive förenkling

**Mer granulär**:
```python
SIMPLIFICATION_TOLERANCES = [95, 90, 75, 50, 25, 15, 5]
```

### Effekt
| Tolerance | Ungefär effekt |
|-----------|----------------|
| p95, p90 | Minimal förenkling (original + små simplifikationer) |
| p75, p50 | Medium förenkling |
| p25, p15 | Aggressive förenkling |
| p5 | Extrem förenkling |

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
