# NMD2023 Klassförteckning

Klasslista hämtad från `NMD2023bas_v2_0.tif.vat.dbf` (Value Attribute Table).
Totalt 52 klasser. Pixelstorlek: 10 m × 10 m (1 px = 100 m² = 0,01 ha).

---

## Bebyggd mark och infrastruktur
*Skyddade klasser — generaliseras aldrig i pipelinen.*

| Värde | Klass |
|------:|-------|
| 51 | Byggnad |
| 52 | Anlagd mark, ej byggnad eller väg/järnväg |
| 53 | Väg eller järnväg |
| 54 | Torvtäkt |

---

## Vatten
*Skyddade klasser — generaliseras aldrig i pipelinen.*

| Värde | Klass |
|------:|-------|
| 61 | Inlandsvatten |
| 62 | Hav |

---

## Åkermark

| Värde | Klass |
|------:|-------|
| 3 | Åkermark |

---

## Skog på fastmark

| Värde | Klass |
|------:|-------|
| 111 | Tallskog på fastmark |
| 112 | Granskog på fastmark |
| 113 | Barrblandskog på fastmark |
| 114 | Lövblandad barrskog på fastmark |
| 115 | Triviallövskog på fastmark |
| 116 | Ädellövskog på fastmark |
| 117 | Triviallövskog med ädellövinslag på fastmark |
| 118 | Temporärt ej skog på fastmark |

---

## Skog på våtmark

| Värde | Klass |
|------:|-------|
| 121 | Tallskog på våtmark |
| 122 | Granskog på våtmark |
| 123 | Barrblandskog på våtmark |
| 124 | Lövblandad barrskog på våtmark |
| 125 | Triviallövskog på våtmark |
| 126 | Ädellövskog på våtmark |
| 127 | Triviallövskog med ädellövinslag på våtmark |
| 128 | Temporärt ej skog på våtmark |

---

## Fjällskog

| Värde | Klass |
|------:|-------|
| 23 | Låg fjällskog på våtmark |
| 43 | Låg fjällskog på fastmark |

---

## Öppen våtmark

| Värde | Klass |
|------:|-------|
| 200 | Öppen våtmark (underindelning saknas) |
| 211 | Buskmyr |
| 212 | Ristuvemyr |
| 213 | Fastmattemyr, mager |
| 214 | Fastmattemyr, frodig |
| 215 | Sumpkärr |
| 216 | Mjukmattemyr |
| 217 | Lösbottenmyr |
| 218 | Övrig öppen myr |

---

## Trädklädd och buskrik våtmark

| Värde | Klass |
|------:|-------|
| 221 | Våtmark med buskar |
| 222 | Risdominerad våtmark |
| 223 | Gräsdominerad våtmark, mager |
| 224 | Gräsdominerad våtmark, frodvuxen |
| 225 | Gräsdominerad våtmark, högvuxen |
| 226 | Mossdominerad våtmark |
| 227 | Våtmark utan växttäcke |
| 228 | Övrig öppen våtmark |

---

## Öppen fastmark

| Värde | Klass |
|------:|-------|
| 411 | Öppen fastmark utan vegetation (ej glaciär eller varaktigt snöfält) |

---

## Buskmark på fastmark

| Värde | Klass |
|------:|-------|
| 4211 | Torr buskdominerad mark |
| 4212 | Frisk buskdominerad mark |
| 4213 | Frisk-fuktig buskdominerad mark |

---

## Risdominerad mark på fastmark

| Värde | Klass |
|------:|-------|
| 4221 | Torr risdominerad mark |
| 4222 | Frisk risdominerad mark |
| 4223 | Frisk-fuktig risdominerad mark |

---

## Gräsmark på fastmark

| Värde | Klass |
|------:|-------|
| 4231 | Torr gräsdominerad mark |
| 4232 | Frisk gräsdominerad mark |
| 4233 | Frisk-fuktig gräsdominerad mark |

---

## Semantisk gruppering i pipelinen

Används av `semantic`-generaliseringsmetoden i steg 6. Grupptilldelning via `nmd_group()`:

| Grupp | Beteckning | Klasser |
|------:|------------|---------|
| 1 | Skog | 111–128 (all skog på fastmark och våtmark) |
| 2 | Våtmark | 200–228, 23 (öppen och trädklädd våtmark, låg fjällskog på våtmark) |
| 3 | Åkermark | 3 |
| 4 | Öppen mark | 411, 4211–4233, 43 (busk/ris/gräsmark, låg fjällskog på fastmark) |
| 5 | Bebyggd/infra | 51–54 (skyddad, slås ej ihop) |
| 6 | Vatten | 61–62 (skyddad, slås ej ihop) |

Semantisk distans mellan grupper (lägre = mer lika, slås ihop hellre):

|   | Skog (1) | Våtmark (2) | Åker (3) | Öppen (4) | Bebyggd (5) | Vatten (6) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Skog (1)** | — | 2 | 3 | 3 | 4 | 5 |
| **Våtmark (2)** | 2 | — | 2 | 1 | 3 | 4 |
| **Åkermark (3)** | 3 | 2 | — | — | 4 | 4 |
| **Öppen mark (4)** | 3 | 1 | — | — | 3 | 4 |
| **Bebyggd (5)** | 4 | 3 | 4 | 3 | — | 4 |
| **Vatten (6)** | 5 | 4 | 4 | 4 | 4 | — |
