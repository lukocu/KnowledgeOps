# Kopiowanie odpowiedzi z cytatami i wąskie okno — Plan Brief

> Full plan: `context/changes/answer-copy-and-narrow-window/plan.md`

## What & Why

Konsultant przekleja odpowiedź asystenta do zgłoszenia. Skopiowany tekst musi więc zachować przy każdej tezie numer cytatu i identyfikator dokumentu (US-01, FR-019). Przepływ pytanie → odpowiedź → dowód ma też działać w oknie 390 px bez przewijania w poziomie (NFR „Szerokość okna”, makieta 1N). To slice S-05 roadmapy.

## Starting Point

S-02 dostarczył odpowiedź z cytatami (1A), abstencję (1C) i panel dowodu. Kopiować można tylko bloki kodu. Układ jest wyłącznie desktopowy: jednorzędowy nagłówek, szyna nawigacji o stałej szerokości i panele boczne o minimalnej szerokości 300 px. Frontend nie ma test runnera.

## Desired End State

Przycisk „Kopiuj odpowiedź z cytatami” (1A) kopiuje zwykły tekst: tezy z `[n]`, kod pod tezą, listę źródeł `[n] doc_id — tytuł` i migawkę. Format sprawdza test w Vitest, uruchamiany w CI. Poniżej 768 px nagłówek ma dwa rzędy, nawigacja jest w szufladzie pod Menu, a dowód i sprawdzone fragmenty otwierają się w modalnym arkuszu od dołu. Przy 390×844 cały przepływ działa z klawiatury i dotykiem, bez przewijania w poziomie. Od 768 px wygląd się nie zmienia.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Format kopii | Zwykły tekst: tezy z `[n]`, kod wcięty, lista źródeł z `doc_id` i tytułem, migawka | Wkleja się czytelnie do każdego systemu zgłoszeń i spełnia kryterium US-01 dosłownie. |
| Narzędzie testu | Vitest (dev), osobny `vitest.config.ts` bez wtyczki React Router | Wybór użytkownika: standard dla Vite, z możliwością rozbudowy o testy komponentów. |
| Próg wąskiego układu | Poniżej 768 px (Tailwind `md`) | Panel 300 px, treść i szyna mieszczą się od ~768 px, więc tablet pionowo zachowuje panel boczny. |
| Arkusz | Natywny `<dialog>` w trybie modalnym, bez zsuwania palcem | Przeglądarka zapewnia pułapkę fokusu i zablokowane tło; zamykają go przycisk, Escape i klik w tło. |
| Weryfikacja 390 px | Ręcznie w panelu przeglądarki (`scrollWidth` w konsoli i zrzuty) | Playwright wymaga backendu, danych i modelu albo mocków, więc należy do osobnego `/10x-e2e-setup`. |
| Escape w arkuszu | `cancel` z `preventDefault()`, Escape dalej obsługuje trasa | Zachowuje istniejącą kolejność zamykania (fragment → lista) i powrót fokusu. |
| Przełączanie układu | Hook `useMediaQuery("(min-width: 768px)")` i klasy `md:` | Wąskie okno zmienia element i zachowanie (dialog, szuflada), czego CSS sam nie zrobi. |

## Scope

**In scope:**
- przycisk kopiowania odpowiedzi;
- `formatAnswerForCopy` z testem;
- Vitest i krok `npm test` w CI;
- wspólny hook `useCopy`;
- nagłówek w dwóch rzędach i szuflada nawigacji;
- marginesy wąskiego okna;
- arkusz dla panelu dowodu i panelu sprawdzonych fragmentów;
- ręczna weryfikacja przy 390×844.

**Out of scope:**
- kopiowanie abstencji i „obu wersji zaleceń” (S-07);
- formaty HTML i Markdown;
- zsuwanie arkusza palcem;
- Playwright;
- testy komponentów w jsdom;
- decyzja otwarta nr 4 (panele poniżej 1400 px);
- ekrany 2, 4 i 5;
- backend i API.

## Architecture / Approach

Czysta funkcja `app/lib/copy-answer.ts` buduje tekst z `AnsweredResult`, a `AnswerView` kopiuje go przez wspólny `useCopy`. Hook `useMediaQuery` mówi, czy okno ma co najmniej 768 px. `AppHeader` i `_layout` używają go dla Menu i szuflady (`NavDrawer`, modalny `<dialog>`). Nowy `PanelFrame` renderuje `aside` albo arkusz `<dialog>`. `AssistantFrame` owija nim cały panel raz, więc arkusz nie zamyka się przy przejściu lista ↔ fragment, a `EvidencePanel` i `CheckedChunksPanel` zwracają samą treść. Stan, Escape i fokus zostają w trasie `answer.tsx`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Kopiowanie odpowiedzi z cytatami | Przycisk z 1A, format z testem w Vitest, `npm test` w CI | Zgodność wersji Vitest z Vite 8 |
| 2. Wąska powłoka (< 768 px) | Nagłówek z 1N, nawigacja w szufladzie, marginesy | Ukryte stałe szerokości albo `nowrap` w komponentach odpowiedzi |
| 3. Arkusz dowodu i weryfikacja 390 px | Panele jako arkusz od dołu, ręczne przejście przepływu | Natywny `<dialog>` kontra Escape i fokus obsługiwane przez trasę |

**Prerequisites:** S-02 zarchiwizowane (jest). Do weryfikacji ręcznej potrzebny jest działający backend z kluczem modelu i zaimportowaną migawką.
**Estimated effort:** ~2–3 sesje, 3 fazy.

## Open Risks & Assumptions

- Wąskie wersje ekranów 2, 4 i 5 nie mają makiet (roadmapa, decyzja 12). S-05 obejmuje tylko asystenta.
- Brak automatycznej ochrony przed regresją szerokości do czasu `/10x-e2e-setup`.

## Success Criteria (Summary)

- Wklejona odpowiedź ma przy każdej tezie numer cytatu, a lista źródeł łączy go z `doc_id`; potwierdza to test w CI.
- Przy 390×844 cały przepływ pytanie → odpowiedź → dowód (i abstencja → fragmenty) działa bez przewijania w poziomie.
- Od 768 px aplikacja wygląda i działa jak przed zmianą.
