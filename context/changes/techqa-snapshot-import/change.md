---
change_id: techqa-snapshot-import
title: Import migawki TechQA i indeks BM25 (S-01)
status: implementing
created: 2026-11-22
updated: 2026-11-23
archived_at: null
---

## Notes

Element S-01 z `context/foundation/roadmap.md`: polecenie CLI w kontenerze backendu importuje migawkę TechQA (rewizja i hashe plików, ograniczona normalizacja, dokładna deduplikacja z mapowaniem identyfikatorów, fragmenty z pochodzeniem, indeks BM25 w pg_search i wyszukiwanie tekstowe PostgreSQL jako punkt odniesienia). Ponowny import tej samej migawki daje identyczny stan.

### Przegląd 2.4 (faza 2, 2026-11-23)

Sześć dokumentów kontrolnych obejrzanych przez `python -m app.techqa.chunking`, potwierdzone przez użytkownika.

- `swg1IT14613`: linie logu (`APPHDL  : 0-270 APPID:`, linie z datą i `LEVEL:`) trafiają do `headings` jako fałszywe nagłówki. Zgodne z oczekiwaniem planu, nie blokuje. Do uwzględnienia w S-04.
- `swg27038676`: gdy sekcja ma długie pojedyncze linie, nakładanie zaczyna się w środku linii (od najbliższego białego znaku). Numery wersji nie są cięte.
- `swg21675316`: puste punktory usunięte; powtórzony kod i linie ` * ` z przykładu zostają (celowo).
- `swg21681142`, `swg21996508`, `swg24033234`: bez uwag.
