# Konfigurerbara Generaliseringsmetoder

## Översikt
Du kan nu enkelt kontrollera vilka generaliseringsmetoder som ska köras i Steg 6-8 genom en enkel inställning i `config.py`.

## Konfiguration

I `src/config.py`, redigera denna rad för att välja vilka metoder som ska köras:

```python
# Möjliga metoder: "conn4", "conn8", "modal", "semantic"
GENERALIZATION_METHODS = {"conn4", "conn8", "modal"}
```

## Tillgängliga Metoder

| Metod | Beskrivning | Tillämpning |
|-------|-------------|------------|
| `conn4` | Sieve-filter med 4-connected struktur | Snabb, mindre aggressive |
| `conn8` | Sieve-filter med 8-connected struktur | Mer aggressive än conn4 |
| `modal` | Modal filter (mode-värde) | Bäst för representativ data |
| `semantic` | Semantisk generalisering | Sparar klassidentitet (långsam) |

## Exempel

### Bara sieve-metoder
```python
GENERALIZATION_METHODS = {"conn4", "conn8"}
```
Resulterar i:
- Steg 6: Kör endast conn4 och conn8 sieve
- Steg 7: Vektoriserar endast dessa två
- Steg 8: Förenklar endast dessa två varianter

### Bara modal (rekommenderat för snabb test)
```python
GENERALIZATION_METHODS = {"modal"}
```
Resulterar i:
- Snabbast möjlig körning (~15 minuter för 4 tiles)
- Bästa visuella resultat för presentation

### Alla metoder
```python
GENERALIZATION_METHODS = {"conn4", "conn8", "modal", "semantic"}
```
Resulterar i:
- Längsta körning (~50+ minuter för 4 tiles)
- Mest omfattande jämförelse

## Hur det Fungerar

1. **Steg 6** läser `GENERALIZATION_METHODS` från config och körandes endast de valda metoderna
2. **Steg 7** läser samma config och vektoriserar endast outputs från steg 6
3. **Steg 8** söker dynamisk efter alla `.gpkg`-filer från steg 7 och förenklar dem

### Automatisk Propagering
Du behöver **INTE** ändra något i steg 7 eller 8! Konfigurationen propageras automatiskt:
- Steg 7 läser `GENERALIZATION_METHODS` från config
- Steg 8 hittar dinamisk vilka GeoPackage-filer som skapades i steg 7

## Performance Påverkan

För 4-tile test-set:
- **Endast modal**: ~15-20 minuter
- **Conn4 + conn8 + modal**: ~50-60 minuter  
- **Alla metoder inkl. semantic**: 70+ minuter

## Standard

Standard-konfigurationen är:
```python
GENERALIZATION_METHODS = {"conn4", "conn8", "modal"}
```

Detta är en bra balans mellan:
- Beräknings-tid
- Antal metoder för jämförelse
- Kvalitet på resultat

## Tips

1. **Snabb test**: Använd `{"modal"}` för snabb körning
2. **Metodjämförelse**: Använd alla fyra för att jämföra resultat
3. **Produktionsmiljö**: Välja only `{"modal"}` för effektivitet
