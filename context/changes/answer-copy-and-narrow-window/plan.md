# Kopiowanie odpowiedzi z cytatami i wąskie okno — plan implementacji

## Overview

S-05 z roadmapy. Konsultant kopiuje odpowiedź tak, że każda teza zachowuje numer cytatu i identyfikator dokumentu (US-01, FR-019). Przepływ pytanie → odpowiedź → dowód (także abstencja ze sprawdzonymi fragmentami) działa w oknie 390 px bez przewijania w poziomie, z dowodem w arkuszu od dołu (makieta 1N, NFR „Szerokość okna”).

## Current State Analysis

- Odpowiedź (`AnswerView`) nie ma przycisku „Kopiuj odpowiedź z cytatami” z makiety 1A. Kopiowanie istnieje tylko dla bloku kodu (`CodeBlock`, stany `idle`/`copied`/`failed` z resetem po 2 s).
- Dane potrzebne do kopii są już w `AnsweredResult`: `claims[].text`, `claims[].code`, `claims[].citation` oraz `citations[].n`, `doc_id`, `title`. `AnswerRecord.snapshot_id` daje migawkę. Backend nie wymaga zmian.
- Układ nie reaguje na szerokość okna:
  - nagłówek to jeden rząd wysokości 44 px (logo, przełącznik ról, DEMO, język, korpus);
  - `NavRail` ma stałą szerokość 56 albo 232 px;
  - panele `EvidencePanel` i `CheckedChunksPanel` to `aside` z `min-w-[300px]`.
  
  Przy 390 px treść jest ściśnięta, a całość wychodzi poza okno.
- Frontend nie ma test runnera. CI frontendu uruchamia lint, format, typecheck i build.
- Brak `context/foundation/lessons.md`.

## Desired End State

- W odpowiedzi jest główny przycisk „Kopiuj odpowiedź z cytatami” (1A), przed statusem „Sprawdzone cytaty”. Kopiuje zwykły tekst: tezy z `[n]`, kod wcięty pod tezą, listę źródeł `[n] doc_id — tytuł` i migawkę. Po kopiowaniu przycisk pokazuje „Skopiowano” albo „Nie skopiowano” (słowo i ikona).
- `npm test` (Vitest) sprawdza format kopii i działa w CI.
- Poniżej 768 px układ odpowiada 1N:
  - nagłówek ma dwa rzędy: Menu, logo, DEMO i PL w pierwszym, przełącznik ról i korpus w drugim;
  - nawigacja jest w szufladzie otwieranej przyciskiem Menu;
  - treść i kompozytor mają marginesy 16 px;
  - dowód i sprawdzone fragmenty otwierają się jako modalny arkusz od dołu.
- Od 768 px układ wygląda jak dziś.
- Przy 390×844 cały przepływ (pytanie, odpowiedź, cytat, nawigacja cytatów, dokument, zamknięcie, abstencja, sprawdzone fragmenty, fragment) przechodzi się klawiaturą i dotykiem, a `document.documentElement.scrollWidth` jest ≤ `window.innerWidth`.

### Key Discoveries:

- Wzorzec kopiowania i stanów przycisku: `frontend/app/components/assistant/AnswerView.tsx:13` (`CodeBlock`).
- Przycisk z makiety: `design/mockups/canvas/S1A.dc.html` („Kopiuj odpowiedź z cytatami”, niebieski główny przycisk, wysokość 36 px, w wierszu ze statusem cytatów).
- Arkusz z makiety: `design/mockups/canvas/S1N.dc.html`:
  - `role="dialog"`, tło `rgba(31,32,35,.4)`, zaokrąglenie 16 px u góry, uchwyt 40×4 px;
  - przyciski nawigacji 40×40 px, stopka z przyciskiem „Dokument” wysokości 40 px;
  - górna krawędź 140 px od góry przy wysokości 844 px.
- Escape i powrót fokusu obsługuje trasa: `frontend/app/routes/answer.tsx` (`onEscape`, `closeCitation`, `closeChunk`, `closeChecked`, `focusSoon`). Panele tylko ustawiają fokus na nagłówku przy otwarciu.
- `vite.config.ts` ładuje `reactRouter()`, który zakłada pełną aplikację. Test czystej funkcji nie powinien go uruchamiać.
- Jedyne breakpointy w kodzie: `xl:px-10` w `AssistantFrame.tsx`.

## What We're NOT Doing

- Kopiowanie abstencji i „obu wersji zaleceń” (FR-019 dla sprzecznych źródeł to S-07).
- Kopiowanie w formacie HTML ani Markdown. Tylko `text/plain`.
- Zsuwanie arkusza palcem. Uchwyt jest tylko wizualny.
- Playwright i automatyczny pomiar `scrollWidth`. Weryfikacja 390 px jest ręczna, a automatyzacja należy do `/10x-e2e-setup` jako osobna praca.
- Testy komponentów w jsdom. Vitest testuje tylko czyste funkcje.
- Decyzja otwarta nr 4 (panele poniżej 1400 px: zwężony panel czy szyna). Od 768 px zostaje obecny zwężony panel.
- Ekrany 2, 4 i 5 (nie istnieją jeszcze w kodzie).
- Zmiany w backendzie i kontrakcie API.

## Implementation Approach

Najpierw kopiowanie, bo jest niezależne od układu i wprowadza Vitest. Potem powłoka wąskiego okna: wspólny hook `useMediaQuery("(min-width: 768px)")` decyduje o układzie. CSS sam nie wystarczy, bo wąskie okno zmienia element (`<dialog>` zamiast `aside`) i zachowanie (modal, szuflada). Na końcu arkusz: obie obudowy paneli przechodzą przez jeden komponent, który renderuje `aside` albo modalny `<dialog>`. Logika trasy (stan, Escape, fokus) zostaje bez zmian.

## Critical Implementation Details

- **Escape w natywnym `<dialog>`:** `showModal()` zamyka dialog sam przy Escape (zdarzenie `cancel`), z pominięciem stanu Reacta. Obudowa musi wywołać `event.preventDefault()` w `cancel` i nic więcej nie robić. Escape dalej obsługuje istniejący `keydown` w trasie (`onEscape`), który decyduje o kolejności zamykania (fragment → lista) i powrocie fokusu. Dialog jest otwierany przez `showModal()` w efekcie po zamontowaniu i zamykany przez odmontowanie (`close()` w sprzątaniu), nigdy przez atrybut `open`.
- **Powrót fokusu po zamknięciu arkusza:** po `close()` przeglądarka przywraca fokus na element aktywny przed `showModal()`. Trasa ustawia fokus w `requestAnimationFrame` (`focusSoon`), więc wygrywa jako druga. Zachowaj tę kolejność: nie przenoś fokusu synchronicznie w sprzątaniu obudowy.
- **Przełączenie szerokości przy otwartym panelu:** zmiana z `aside` na `<dialog>` przemontowuje treść panelu, więc okno kontekstu i tryb dokumentu wracają do domyślnych. To akceptowalne. Stan cytatu (`activeN`, `opened`) jest w trasie i się nie gubi.

## Faza 1: Kopiowanie odpowiedzi z cytatami

### Overview

Czysta funkcja formatująca z testem w Vitest, przycisk w odpowiedzi, wspólny hook stanów kopiowania i krok `npm test` w CI.

### Changes Required:

#### 1. Vitest

**File**: `frontend/package.json`, `frontend/vitest.config.ts`, `frontend/package-lock.json`

**Intent**: Dodaj Vitest jako zależność deweloperską (wersja zgodna z Vite 8, `npm i -D vitest`). Dodaj skrypt `test`. Osobny plik konfiguracji testów nie ładuje `reactRouter()` ani Tailwinda, więc testy nie zależą od builda aplikacji.

**Contract**: skrypt `"test": "vitest run"`. `vitest.config.ts` z `defineConfig` z `vitest/config`, `test.environment: "node"`, `test.include: ["app/**/*.test.ts"]`. Testy importują `describe`/`it`/`expect` z `vitest` jawnie (bez globali, bez zmian w `tsconfig.json` `types`). ESLint i `tsc` obejmują nowe pliki przez istniejące `include: ["**/*"]`.

#### 2. Format kopii

**File**: `frontend/app/lib/copy-answer.ts`, `frontend/app/lib/copy-answer.test.ts`

**Intent**: Funkcja buduje zwykły tekst odpowiedzi do schowka. Każda teza zachowuje numer cytatu, a lista źródeł łączy numer z identyfikatorem dokumentu (kryterium US-01). Etykiety przychodzą z zewnątrz, więc funkcja nie zależy od i18n.

**Contract**: `formatAnswerForCopy(result: AnsweredResult, snapshotId: string, labels: { sources: string; snapshot: string }): string`. Import typu przez `import type` z `../api/answers`. Format (linie rozdzielone `\n`):

```
<teza 1> [1]
    <kod tezy 1, każda linia wcięta 4 spacjami>
<teza 2> [2]

<labels.sources>:
[1] <doc_id> — <title>
[2] <doc_id> — <title>
<labels.snapshot>: <snapshotShort(snapshotId)>
```

- Kolejność tez jak w `result.claims`.
- Źródła posortowane rosnąco po `n`, każde raz.
- `omitted_claims` są pomijane.
- Teza bez kodu nie ma linii kodu.
- Na końcu jest jeden znak nowej linii.
- Migawkę skróć istniejącym `snapshotShort` z `app/lib/snapshot.ts` (czysta funkcja, bez modułów przeglądarkowych).

Testy sprawdzają:
- każda teza kończy się `[n]` swojego cytatu;
- każdy `[n]` ma w liście źródeł linię z `doc_id`;
- kod jest wcięty pod właściwą tezą;
- dwie tezy z tym samym cytatem dają jedną linię źródła;
- pominięte tezy nie trafiają do kopii;
- wynik dla stałego przykładu jest równy oczekiwanemu tekstowi.

#### 3. Wspólny stan kopiowania

**File**: `frontend/app/components/assistant/useCopy.ts`, `frontend/app/components/assistant/AnswerView.tsx`

**Intent**: Wydziel z `CodeBlock` logikę `navigator.clipboard.writeText` i stanów z resetem po 2 s, żeby przycisk kodu i przycisk odpowiedzi działały tak samo.

**Contract**: `useCopy(): { state: "idle" | "copied" | "failed"; copy: (text: string) => Promise<void> }`. `CodeBlock` korzysta z hooka bez zmiany wyglądu ani tekstów.

#### 4. Przycisk „Kopiuj odpowiedź z cytatami”

**File**: `frontend/app/components/assistant/AnswerView.tsx`, `frontend/app/i18n/pl.ts`, `frontend/app/i18n/en.ts`

**Intent**: Dodaj główny przycisk z 1A na początku wiersza ze statusem „Sprawdzone cytaty” i „Otwórz wszystkie cytaty”. Przycisk kopiuje wynik `formatAnswerForCopy`. Status kopiowania jest pokazany słowem i ikoną (jak w `CodeBlock`) i ogłaszany czytnikom ekranu.

**Contract**: przycisk `type="button"`, styl z 1A (tło `bg-primary`, biały tekst, `h-9`, `px-4`, `rounded-lg`, ikona kopiowania). Nowe klucze i18n, PL jako baza, EN typowany kluczami PL:
- `answer.copyAnswer` („Kopiuj odpowiedź z cytatami” / „Copy answer with citations”);
- `answer.copySources` („Źródła” / „Sources”);
- `answer.copySnapshot` („Migawka” / „Snapshot”).

Teksty `answer.copied` i `answer.copyFailed` są używane ponownie. Tekst i ikona przycisku zmieniają się jak w `CodeBlock`. Wynik („Skopiowano” albo „Nie skopiowano”) trafia dodatkowo do ukrytego wizualnie elementu `role="status"` obok przycisku, bo sama zmiana tekstu przycisku zwykle nie jest ogłaszana przez czytniki ekranu (przegląd planu, F3).

#### 5. CI

**File**: `.github/workflows/ci.yml`

**Intent**: Uruchamiaj testy frontendu w CI.

**Contract**: w jobie frontendu krok `- run: npm test` po `npm run typecheck`, przed `npm run build`.

#### 6. AGENTS.md

**File**: `AGENTS.md`

**Intent**: Lista kontroli frontendu obejmuje `npm test`.

**Contract**: linia „Kontrole frontendu” dostaje `npm test` (Vitest, czyste funkcje w `app/**/*.test.ts`).

### Success Criteria:

#### Automated Verification:

- Testy frontendu przechodzą: `cd frontend; npm test`
- Lint, format i typy przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck`
- Build przechodzi: `cd frontend; npm run build`

#### Manual Verification:

- Kopia odpowiedzi z kodem, wklejona do edytora tekstu, ma przy każdej tezie `[n]`, kod pod tezą i listę źródeł z `doc_id`
- Przycisk pokazuje „Skopiowano” z ikoną i po 2 s wraca do stanu początkowego; „Kopiuj” przy bloku kodu działa jak wcześniej

**Implementation Note**: Po fazie 1 i zielonych kontrolach automatycznych zatrzymaj się na ręczne potwierdzenie.

---

## Faza 2: Wąska powłoka (< 768 px)

### Overview

Hook szerokości okna, nagłówek w dwóch rzędach, nawigacja w szufladzie i mniejsze marginesy treści poniżej 768 px.

### Changes Required:

#### 1. Hook szerokości

**File**: `frontend/app/lib/use-media-query.ts`

**Intent**: Jedno źródło prawdy o tym, czy okno jest szerokie. Komponenty, które zmieniają element albo zachowanie (szuflada, arkusz), pytają hooka. Czysto wizualne różnice robią klasy Tailwind `md:`.

**Contract**: `useMediaQuery(query: string): boolean` oparty na `window.matchMedia` i `useSyncExternalStore` (`getServerSnapshot` zwraca `true`, bo SPA i tak renderuje w przeglądarce). Stała `WIDE_QUERY = "(min-width: 768px)"`, zgodna z Tailwind `md`.

#### 2. Nagłówek w wąskim oknie

**File**: `frontend/app/components/shell/AppHeader.tsx`

**Intent**: Poniżej 768 px nagłówek ma układ z 1N:
- pierwszy rząd: przycisk Menu (36×36 px), logo i nazwa, a po prawej DEMO i PL;
- drugi rząd: przełącznik ról i etykieta korpusu (z tym samym `title` z migawką).

Od 768 px nagłówek się nie zmienia.

**Contract**: `AppHeader` dostaje `onOpenMenu: () => void` i renderuje przycisk Menu tylko w wąskim oknie (`aria-label` i `title` z nowego klucza `nav.menu`: „Menu”, z `aria-expanded` i `aria-controls` szuflady). Żaden element nagłówka nie znika w wąskim oknie.

#### 3. Nawigacja w szufladzie

**File**: `frontend/app/components/shell/NavRail.tsx`, `frontend/app/routes/_layout.tsx`

**Intent**: W wąskim oknie szyna nawigacji jest ukryta, a te same pozycje są w szufladzie z lewej (modalny `<dialog>`). Szufladę zamyka przycisk Zamknij, Escape, klik w tło albo wybór pozycji. Fokus wraca na przycisk Menu. Układ trasy trzyma stan otwarcia.

**Contract**:
- Pozycje nawigacji (`NAV_ITEMS`) renderuje jeden komponent listy, używany przez szynę i szufladę.
- `NavRail` renderuje się tylko w szerokim oknie.
- Nowy `NavDrawer({ open, onClose })` jest w tym samym pliku albo w `shell/NavDrawer.tsx`: `<dialog>` przez `showModal()`, szerokość `min(280px, 85vw)`, tło jak w 1N, `cancel` z `preventDefault()` i wywołaniem `onClose`, przewijana lista z `overscroll-contain`.
- Nowy klucz `nav.close`.

#### 4. Marginesy treści

**File**: `frontend/app/components/assistant/AssistantFrame.tsx`, `frontend/app/routes/assistant.tsx` (jeśli ma własne marginesy)

**Intent**: Poniżej 768 px treść i kompozytor mają marginesy 16 px jak w 1N. Od 768 px zostają obecne `px-6 xl:px-10`.

**Contract**: klasy `px-4 md:px-6 xl:px-10` i podobnie dla górnego odstępu treści (`pt-4 md:pt-7`). Sprawdź `Composer`, `QuestionBubble`, `SourcesRow`, `PreparationDetails` i `ProgressCard` pod kątem stałych szerokości albo `whitespace-nowrap` bez zawijania, które mogłyby wyjść poza 390 px. Popraw tylko to, co realnie wychodzi.

### Success Criteria:

#### Automated Verification:

- Testy, lint, format i typy przechodzą: `cd frontend; npm test; npm run lint; npm run format:check; npm run typecheck`
- Build przechodzi: `cd frontend; npm run build`

#### Manual Verification:

- Przy 390×844 nagłówek ma dwa rzędy jak 1N, a przy 1280 px wygląda jak przed zmianą
- Menu otwiera szufladę z nawigacją; Escape, klik w tło i Zamknij ją zamykają, a fokus wraca na Menu
- Ekran startowy asystenta i odpowiedź przy 390 px nie przewijają się w poziomie (`document.documentElement.scrollWidth <= window.innerWidth` w konsoli)

**Implementation Note**: Po fazie 2 i zielonych kontrolach automatycznych zatrzymaj się na ręczne potwierdzenie.

---

## Faza 3: Arkusz dowodu i weryfikacja 390 px

### Overview

Wspólna obudowa paneli: od 768 px `aside` jak dziś, poniżej modalny arkusz od dołu z 1N. Na koniec ręczne przejście całego przepływu przy 390×844.

### Changes Required:

#### 1. Obudowa panelu

**File**: `frontend/app/components/assistant/PanelFrame.tsx`, `frontend/app/components/assistant/AssistantFrame.tsx`, `frontend/app/routes/answer.tsx`

**Intent**: Jeden komponent decyduje, czy panel jest bocznym `aside`, czy arkuszem. Oba panele (dowód i sprawdzone fragmenty) mają przez to takie samo zachowanie w wąskim oknie. Obudowa jest renderowana raz, w `AssistantFrame`, wokół całego `panel`. Dzięki temu `<dialog>` żyje przez całe otwarcie, także przy przejściu lista sprawdzonych fragmentów ↔ fragment, które w trasie przełącza `CheckedChunksPanel` na `EvidencePanel`. Inaczej każde takie przejście zamykałoby i otwierało arkusz, z mignięciem tła i skokiem fokusu (przegląd planu, F1).

**Contract**: `PanelFrame({ label, variant, onDismiss, children })`, gdzie `variant: "evidence" | "checked"` wybiera szerokość i tło szerokiego `aside`. Szerokości bez zmian: `w-[min(400px,45%)]` albo `w-[min(420px,45%)]`, `min-w-[300px]`.

`AssistantFrame` dostaje opcjonalne `panelFrame?: { label: string; variant: "evidence" | "checked"; onDismiss: () => void }` i owija nim `panel`, gdy ten jest niepusty. Trasa `answer.tsx` wylicza je razem z `panel`:
- cytat: `evidence`, `onDismiss` to `closeCitation`;
- fragment abstencji: `checked`, `onDismiss` to `closeChunk`;
- lista sprawdzonych fragmentów: `checked`, `onDismiss` to `closeChecked`.

Wariant `checked` obejmuje też fragment, żeby szeroki panel nie zmieniał szerokości przy przejściu. `label` to dotychczasowe `evidence.panel` albo `checked.panel`. `PanelFrame` się nie przemontowuje, więc efekt z `showModal()` zależy tylko od zamontowania, a zmiana `label` aktualizuje sam atrybut.

W wąskim oknie (`useMediaQuery(WIDE_QUERY)` jest `false`):
- `<dialog aria-label={label}>` otwierany w efekcie przez `showModal()`;
- przyklejony do dołu, pełna szerokość, `max-height: calc(100dvh - 140px)` (wysokość jak w 1N), zaokrąglenie 16 px u góry, cień jak w 1N;
- tło przez `::backdrop` w kolorze `rgba(31,32,35,.4)`;
- uchwyt 40×4 px na górze (`aria-hidden`);
- klik w tło (`event.target === dialog`) wywołuje `onDismiss`;
- `cancel` tylko `preventDefault()`, bo Escape obsługuje trasa (patrz Critical Implementation Details);
- przewija się treść arkusza, nie strona pod nim; przewijany element arkusza ma `overscroll-behavior: contain` (`overscroll-contain`), żeby przewinięcie dotykiem do końca nie przechodziło na stronę (przegląd planu, F2).

#### 2. Panele w obudowie

**File**: `frontend/app/components/assistant/EvidencePanel.tsx`, `frontend/app/components/assistant/CheckedChunksPanel.tsx`

**Intent**: Panele usuwają własny `aside` i zwracają samą treść, bo obudowę daje `AssistantFrame`. W wąskim oknie przyciski w nagłówku (poprzedni, następny, zamknij) i w stopce („Dokument” albo „Okno kontekstu”) mają 40 px wysokości, a marginesy poziome 16 px, jak w 1N.

**Contract**: Panele zachowują swoje propsy i `onClose`. Korzeń panelu to `div` wypełniający obudowę (`flex min-h-0 flex-1 flex-col`), z dotychczasowym tłem i przewijaniem. Fokus na nagłówku przy otwarciu zostaje. Rozmiary wąskiego wariantu przez klasy `md:` (np. `h-10 w-10 md:h-8 md:w-8`, `px-4 md:px-6`). Stan, Escape i powrót fokusu w trasie bez zmian.

### Success Criteria:

#### Automated Verification:

- Testy, lint, format i typy przechodzą: `cd frontend; npm test; npm run lint; npm run format:check; npm run typecheck`
- Build przechodzi: `cd frontend; npm run build`

#### Manual Verification:

- Przy 390×844 cytat otwiera arkusz od dołu z tłem; poprzedni i następny przełączają cytat, „Dokument” pokazuje dokument, a Zamknij, Escape i klik w tło zamykają arkusz, z fokusem z powrotem na cytacie
- Przy 390×844 abstencja otwiera sprawdzone fragmenty w arkuszu, fragment otwiera się w arkuszu, Escape wraca z fragmentu do listy, a potem zamyka listę
- Tab nie wychodzi poza otwarty arkusz, a tło nie przewija się pod arkuszem
- Cały przepływ pytanie → odpowiedź → dowód → kopiowanie przy 390×844 nie przewija się w poziomie (`scrollWidth <= innerWidth` w każdym stanie); zrzuty odpowiedzi i arkusza są zapisane
- Przy 1280 px panele boczne wyglądają i działają jak przed zmianą

**Implementation Note**: Po fazie 3 i zielonych kontrolach automatycznych zatrzymaj się na ręczne potwierdzenie.

---

## Testing Strategy

### Unit Tests:

- `formatAnswerForCopy`: numer cytatu przy każdej tezie, `doc_id` dla każdego numeru, kod pod tezą, deduplikacja źródeł, pominięte tezy, pełny tekst dla stałego przykładu.

### Integration Tests:

- Brak w tym etapie. Przepływ w przeglądarce sprawdzamy ręcznie. Automatyzacja to osobna praca (`/10x-e2e-setup`).

### Manual Testing Steps:

1. Backend z kluczem modelu i zaimportowaną migawką, `npm run dev`, panel przeglądarki 1280 px: pytanie z odpowiedzią, kopiowanie, wklejenie do edytora.
2. Zmiana rozmiaru na 390×844: nagłówek, Menu i szuflada, odpowiedź, cytat w arkuszu, nawigacja cytatów, dokument, zamknięcie na trzy sposoby.
3. Pytanie bez dowodów (abstencja) przy 390×844: sprawdzone fragmenty, fragment, Escape dwa razy.
4. W każdym stanie w konsoli: `document.documentElement.scrollWidth <= window.innerWidth`.
5. Powrót do 1280 px przy otwartym panelu: panel boczny wraca, stan cytatu się nie gubi.

## Performance Considerations

Brak istotnych. `matchMedia` z `useSyncExternalStore` nie renderuje ponownie przy każdej zmianie rozmiaru, tylko przy przekroczeniu progu.

## Migration Notes

Brak. Tylko frontend, bez zmian w danych i API.

## References

- Roadmapa: `context/foundation/roadmap.md` (S-05)
- PRD: US-01, FR-019, NFR „Szerokość okna” w `context/foundation/prd.md`
- Makiety: `design/mockups/canvas/S1A.dc.html`, `design/mockups/canvas/S1N.dc.html`, `design/mockups/README.md`
- Poprzednia zmiana: `context/archive/2026-11-23-grounded-answer-or-abstention/plan.md`
- Wzorzec kopiowania: `frontend/app/components/assistant/AnswerView.tsx:13`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Kopiowanie odpowiedzi z cytatami

#### Automated

- [x] 1.1 Testy frontendu przechodzą: `cd frontend; npm test`
- [x] 1.2 Lint, format i typy przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck`
- [x] 1.3 Build przechodzi: `cd frontend; npm run build`

#### Manual

- [x] 1.4 Kopia odpowiedzi z kodem, wklejona do edytora tekstu, ma przy każdej tezie `[n]`, kod pod tezą i listę źródeł z `doc_id`
- [x] 1.5 Przycisk pokazuje „Skopiowano” z ikoną i po 2 s wraca do stanu początkowego; „Kopiuj” przy bloku kodu działa jak wcześniej

### Phase 2: Wąska powłoka (< 768 px)

#### Automated

- [ ] 2.1 Testy, lint, format i typy przechodzą: `cd frontend; npm test; npm run lint; npm run format:check; npm run typecheck`
- [ ] 2.2 Build przechodzi: `cd frontend; npm run build`

#### Manual

- [ ] 2.3 Przy 390×844 nagłówek ma dwa rzędy jak 1N, a przy 1280 px wygląda jak przed zmianą
- [ ] 2.4 Menu otwiera szufladę z nawigacją; Escape, klik w tło i Zamknij ją zamykają, a fokus wraca na Menu
- [ ] 2.5 Ekran startowy asystenta i odpowiedź przy 390 px nie przewijają się w poziomie

### Phase 3: Arkusz dowodu i weryfikacja 390 px

#### Automated

- [ ] 3.1 Testy, lint, format i typy przechodzą: `cd frontend; npm test; npm run lint; npm run format:check; npm run typecheck`
- [ ] 3.2 Build przechodzi: `cd frontend; npm run build`

#### Manual

- [ ] 3.3 Przy 390×844 cytat otwiera arkusz od dołu; nawigacja cytatów, „Dokument” i trzy sposoby zamknięcia działają, fokus wraca na cytat
- [ ] 3.4 Przy 390×844 abstencja: sprawdzone fragmenty i fragment w arkuszu, Escape wraca z fragmentu do listy, potem zamyka listę
- [ ] 3.5 Tab nie wychodzi poza otwarty arkusz, a tło nie przewija się pod arkuszem
- [ ] 3.6 Cały przepływ przy 390×844 bez przewijania w poziomie (`scrollWidth <= innerWidth` w każdym stanie), zrzuty zapisane
- [ ] 3.7 Przy 1280 px panele boczne wyglądają i działają jak przed zmianą
