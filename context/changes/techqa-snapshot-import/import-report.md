# Raport z pełnego przebiegu importu TechQA (S-01)

Data: 2026-11-23. Środowisko: obraz bazy `paradedb/paradedb:0.27.0-pg18`, backend z Compose (`docker compose run --rm backend python -m app.cli ...`), Docker Desktop na Windows.

## Import (dwa przebiegi)

| | Pierwszy | Drugi |
| --- | --- | --- |
| Dokumenty / kanoniczne | 28 481 / 28 478 | 28 481 / 28 478 |
| Grupy duplikatów | 2 | 2 |
| Fragmenty (mediana, maksimum na dokument) | 105 450 (3, 159) | 105 450 (3, 159) |
| Dokumenty bez fragmentów | 0 | 0 |
| `train.json`: rekordy, odwołania, różne dokumenty, braki | 910, 610, 496, 0 | 910, 610, 496, 0 |
| Zapis | 22,2 s | 25,8 s |
| Weryfikacja, normalizacja i chunking, hash stanu | 1,3 s, 2,0 s, 0,9 s | 1,3 s, 2,0 s, 1,0 s |
| Porównanie z poprzednim | pierwszy import | identyczny |

`state_sha256` w obu przebiegach: `3981ae29e8406ad9fbb59591d77f5babee768f733d76ca0ac35b26f0414b8eb9`.

Grupy duplikatów: `ssg1S1010476` ← `ssg1S1010477`, `ssg1S1010478`; `swg21448977` ← `swg21454120`.

## Zapytania kontrolne (top 10)

Zapytaniem jest pierwsza linia pytania z `train.json`. Format: pozycja. dokument/numer fragmentu (wynik). Oczekiwany dokument według `train.json` jest pogrubiony.

### TRAIN_Q000 — oczekiwany `swg21996508`

- **BM25: pozycja 1.** **swg21996508/0** (37,096); swg1IT18432/0 (32,374); swg21993387/2; swg21535534/0; swg21684407/0; swg21420884/0; swg1IZ63086/1; swg21693623/3; swg1IC97695/3; swg1PI60955/1.
- **FTS: pozycja 3** (6 wyników). swg21974124/2 (0,200); swg21978471/2 (0,200); **swg21996508/0** (0,200); swg1IT18432/0; swg21974116/2; swg22003596/3.

### TRAIN_Q001 — oczekiwany `swg21675316`

- **BM25: pozycje 1 i 10.** **swg21675316/0** (45,149); swg21675015/3; swg21500040/0; swg1IV51846/0; swg21500051/0; swg21676634/0; swg1IY88286/1; swg21676634/2; swg21421783/0; **swg21675316/1** (29,836).
- **FTS: 0 wyników.** `websearch_to_tsquery` łączy wszystkie słowa operatorem AND, więc długie pytanie nic nie zwraca.

### TRAIN_Q003 — oczekiwany `swg21179559`

- **BM25: poza top 10.** swg21260155/1 (33,833); swg21260155/0; swg21973130/0; nas8N1020262/1; nas8N1020262/0; nas8N1020262/2; swg1IY51525/3; swg1IY54532/1; swg21648889/2; swg21636093/4.
- **FTS: poza top 10** (2 wyniki). nas8N1020262/2 (0,008); swg1HE12059/1 (0,001).

## Wnioski dla kolejnych etapów

- BM25 znajduje oczekiwany dokument dla dwóch z trzech pytań (pozycja 1). Dla Q003 oczekiwanego dokumentu nie ma w top 10, więc to przypadek do obejrzenia w S-02 (Recall@k), nie błąd importu.
- FTS jako punkt odniesienia jest słaby przy pełnych pytaniach, bo zapytanie jest iloczynem wszystkich słów. To zachowanie `websearch_to_tsquery`, nie błąd. Porównanie metod w S-02 powinno to uwzględnić.
- Pytania nie mają w `train.json` pola `answerable` (wartość `None`), więc podział na odpowiadalne i nie jest tu dostępny. To temat S-04.
