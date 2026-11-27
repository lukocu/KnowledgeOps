---
date: 2026-11-27T10:19:27+01:00
researcher: Antigravity
git_commit: 4d47785
branch: main
repository: KnowledgeOps
topic: "S-09: Decyzja redaktora i historia analizy (editor-decision-and-history)"
tags: [research, codebase, auditing, decisions, history, frontend, mockups, ai-devs-4]
status: complete
last_updated: 2026-11-27
last_updated_by: Antigravity
---

# Research: S-09 — Decyzja redaktora i historia analizy (`editor-decision-and-history`)

**Date**: 2026-11-27T10:19:27+01:00
**Researcher**: Antigravity
**Git Commit**: `4d47785`
**Branch**: `main`
**Repository**: `KnowledgeOps`

## Research Question

Jak obecna implementacja audytu po S-08 (`resolved-case-audit`), schemat ParadeDB, API FastAPI, makiety kanwy (`3`, `3N`, `3N-D`), wymagania PRD (`US-02`, `FR-009`, `FR-021`, `FR-011`) oraz wzorce z modułu AI Devs 4 (`04_05_review`) definiują architekturę i kontrakt dla etapu **S-09 (`editor-decision-and-history`)**?

## Summary

1. **Baza danych (ParadeDB):** W `backend/migrations/` istnieją dokładnie 4 migracje (`0001`–`0004`), z których `0004_audits.sql` tworzy 2 tabele: `audits` i `audit_claims` (tabela `audit_steps` nie istnieje w sprawdzonej bazie kodu). Migracje `0001`–`0004` są niezmienne (weryfikowane SHA-256 w `backend/app/migrations.py:39-61`). S-09 wymaga addytywnej migracji `0005_*.sql` z dwiema nowymi tabelami: bieżące decyzje per teza (`audit_claim_decisions` z `CHECK (btrim(justification) <> '')`, 4 kategoriami decyzji i `role_label`) oraz niemutowalna oś zdarzeń (`audit_events`) do realizacji `FR-021`.
2. **Cykl życia analizy vs status decyzji:** `audits.status` (`0004_audits.sql:12`) ma dokładnie 4 wartości cyklu wykonania (`queued`, `running`, `completed`, `failed`). Status „zapisana” (`prd.md:109`, `roadmap.md:346`) nie powinien nadpisywać `audits.status`; powinien być osobnym polem wyliczanym (`decision_status`: np. `pending` / `in_progress` / `saved`, gdzie `saved` zachodzi wyłącznie, gdy `audits.status == 'completed'`, `claims_total > 0` oraz liczba tez z decyzją równa się `claims_total`).
3. **API i przepływ danych:** `backend/app/api/audits.py` udostępnia obecnie 2 endpointy (`POST /api/audits` i `GET /api/audits/{audit_id}`), gdzie `GET` wymaga ciasteczka `kops_session` przez `AuditSessionDep` (`session.py:69-71`, zwrot `404` przy braku sesji). S-09 dopina endpoint zapisu/aktualizacji decyzji per teza (`PUT /api/audits/{audit_id}/claims/{claim_id}/decision`) i rozszerza odpowiedź `GET /api/audits/{audit_id}` o `decision` na każdej tezie, `decision_status`, `decisions_count` oraz `history`. Zapis decyzji nie wywołuje LLM ani Langfuse (`observability.py` i `runner.py` nie wymagają zmian); dane zostają wyłącznie w ParadeDB.
4. **Frontend i makiety (`3`, `3N`, `3N-D`):** `AuditResultView.tsx` ma już lewą i środkową kolumnę ekranu `3` oraz wspólny prawy slot `PanelFrame` (desktop `>= 768 px` jako `<aside>`, mobile `< 768 px` jako natywny `<dialog>.showModal()` bottom sheet z trapem fokusu i uchwytem). Makiety `S3.dc.html:26`, `S3N.dc.html:26` i `S3ND.dc.html:26` specyfikują prawy panel decyzji (`340 px` na desktopie), dolny pasek CTA na `390 px`, arkusz `3N-D`, 4 kategorie decyzji bez wyboru domyślnego, wymagane pole uzasadnienia i zwinięty `<details>` `Historia` nad `Jak powstała ta analiza`.
5. **Wzorce AI Devs 4 (`04_05_review`) i granica MVP:** Warto przenieść deterministyczną nawigację po elementach, blokowanie akcji podczas trwania analizy/zapisu, guard `isEditableTarget()` dla skrótów klawiszowych oraz autorytatywny zwrot zaktualizowanego stanu z serwera. Bezwzględnie wykluczamy wszelkie mechanizmy edycji/patchowania/cofania tekstu dokumentów oraz podsumowywania zmian przez LLM — zapis decyzji w KnowledgeOps nigdy nie modyfikuje dokumentacji (`AGENTS.md`, `prd.md:107,253`).
6. **Rozbieżności i decyzje dla `/10x-plan`:** Zidentyfikowano 6 konkretnych rozbieżności między makietami, PRD a kodem S-08 (m.in. linia „Sugestia systemu” w makiecie nieobecna w PRD, zachowanie roli `consultant` na ekranie `3`, współistnienie stałego panelu decyzji z `EvidencePanel`/`CaseContextPanel` na `1280 px`, etykieta „szkic” w historii makiety, brak progresu `X/N` na makiecie `S3`, semantyka `is_demo` z S-10).

---

## Detailed Findings

### 1. Backend: schemat ParadeDB, `store.py`, cykl życia i API

- **Istniejące migracje (`backend/migrations/`):** Katalog zawiera dokładnie 4 pliki: `0001_techqa_schema.sql`, `0002_answers.sql`, `0003_synthetic_and_conflicts.sql`, `0004_audits.sql`. Kolejną migracją jest `0005_*.sql`. Istniejące pliki migracji nie mogą być edytowane, bo `backend/app/migrations.py:39-61` weryfikuje ich SHA-256.
- **Tabela `audits` (`backend/migrations/0004_audits.sql:5-39`):**
  - Klucz główny: `id uuid PRIMARY KEY` (`:6`), celowo bez kluczy obcych do `snapshots`/`documents`/`chunks` (`:1-4`), dzięki czemu ponowny `import-techqa` nie usuwa audytów.
  - Zakres sesji i demo: `session_hash text NOT NULL` (`:7`), `is_demo boolean NOT NULL DEFAULT false` (`:8`), indeks `audits_session_created_idx ON audits (session_hash, created_at DESC)` (`:62`).
  - Status wykonania: `status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed'))` (`:12`) oraz `stage text NOT NULL CHECK (stage IN ('queued', 'extracting', 'retrieving', 'verifying', 'aggregating', 'completed', 'failed'))` (`:13-23`).
  - Wyniki i postęp: `claims_total` (`:24`), `claims_done` (`:25`), `note_verdict CHECK (note_verdict IN ('full', 'partial', 'contradiction', 'insufficient'))` (`:26-28`), `case_context jsonb` (`:29`), znaczniki `created_at` (`:36`), `updated_at` (`:37`), `completed_at` (`:38`).
- **Tabela `audit_claims` (`backend/migrations/0004_audits.sql:41-60`):**
  - Klucz główny: `id uuid PRIMARY KEY` (`:42`), FK `audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE` (`:43`), `UNIQUE (audit_id, claim_index)` (`:59`), indeks `audit_claims_audit_idx ON audit_claims (audit_id, claim_index)` (`:63`).
  - Ocena systemu: `verdict text NOT NULL CHECK (verdict IN ('supported', 'contradicted', 'insufficient'))` (`:51-53`), `rationale` (`:54`), `scope_note` (`:55`), `evidence jsonb` (`:56`), `checked_docs jsonb` (`:57`), `error` (`:58`).
- **Brak tabel pośrednich i historycznych:** W sprawdzonym katalogu `backend/` nie istnieje tabela `audit_steps` ani żadne kolumny/tabele dla decyzji redaktora i zdarzeń historii.
- **Kandydat na schemat `0005_*.sql`:**
  1. `audit_claim_decisions` (oddzielona od oceny systemu zgodnie z `prd.md:221`):
     - `id uuid PRIMARY KEY`
     - `audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE`
     - `claim_id uuid NOT NULL REFERENCES audit_claims(id) ON DELETE CASCADE`
     - `decision text NOT NULL CHECK (decision IN ('agree_with_system', 'request_source_or_verify', 'consider_doc_update', 'system_verdict_wrong'))` (4 kategorie startowe z `prd.md:110`, nazwy kodowe do ustalenia w planie)
     - `justification text NOT NULL CHECK (btrim(justification) <> '')` (wymagane niepuste uzasadnienie, `prd.md:109`)
     - `role_label text NOT NULL CHECK (role_label IN ('editor', 'consultant'))` (etykieta roli, `prd.md:237`)
     - `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()`
     - `UNIQUE (claim_id)` (lub `UNIQUE (claim_id, session_hash)`, jeśli w S-10 odwiedzający mają móc zapisywać decyzje na współdzielonych przykładach `is_demo = true` bez wzajemnego nadpisywania — do rozstrzygnięcia w planie).
  2. `audit_events` (append-only dla `FR-021`):
     - `id uuid PRIMARY KEY`, `audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE`, `claim_id uuid REFERENCES audit_claims(id) ON DELETE CASCADE` (nullable dla zdarzeń na poziomie całej analizy)
     - `event_type text NOT NULL CHECK (event_type IN ('audit_created', 'evaluation_completed', 'evaluation_failed', 'decision_saved', 'decision_updated'))`
     - `actor_type text NOT NULL CHECK (actor_type IN ('system', 'human'))`, `role_label text` (nullable dla `system`)
     - `payload jsonb NOT NULL DEFAULT '{}'::jsonb`
     - `created_at timestamptz NOT NULL DEFAULT now()`
     - Indeks: `(audit_id, created_at ASC, id ASC)`.
  - Zapis zdarzeń systemowych w `backend/app/auditing/store.py` można wpiąć atomowo w istniejące bloki `conn.transaction()` w `create_audit` (`:93-126`), `complete_audit` (`:161-229`), `fail_audit` (`:232-252`) oraz `fail_orphaned_audits` (`:255-271`). Dla audytów utworzonych przed migracją `0005` historia może zostać albo uzupełniona jednorazowo w samej migracji z `audits.created_at`/`completed_at`, albo odczytana jako pusta dla starszych rekordów (do rozstrzygnięcia w planie).
- **Rozdział `audits.status` od `decision_status`:**
  - `audits.status` steruje pollingiem na froncie (`audit-detail.tsx:41-74`) i sprzątaniem osieroconych zadań na starcie backendu (`main.py:39`, `store.py:255-271`).
  - Status decyzji powinien być osobnym polem wyliczanym w odpowiedzi API (np. `decision_status`: `pending` / `in_progress` / `saved` + `decisions_count: int`), gdzie `saved` zachodzi dokładnie wtedy, gdy `audits.status == 'completed'`, `claims_total > 0` oraz `decisions_count == claims_total`. Zapewnia to zgodność z NFR (`prd.md:221`) oraz z przyszłymi osobnymi kolumnami filtrów w S-10 (`prd.md:141,144`).
- **Kontrakt API (`backend/app/api/audits.py`):**
  - Obecnie: `POST /api/audits` (`202 Accepted`, `audits.py:167-248`, używa `SessionDep` z `session.py:31-48,67`) oraz `GET /api/audits/{audit_id}` (`audits.py:251-265`, używa `AuditSessionDep` z `session.py:51-62,69-71`, zwraca `404` przy braku/niezgodności sesji).
  - Pula połączeń DB ma `max_size=5` (`backend/app/db.py:25`), a wszystkie funkcje w `store.py` przyjmują `AsyncConnection` i utrzymują krótkie transakcje.
  - Nowy endpoint S-09: `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` (wymaga `AuditSessionDep`, weryfikuje własność audytu → `404`, `audit.status == "completed"` → `409 Conflict` w innym stanie, przynależność `claim_id` do `audit_id` → `404`, niepuste `justification` i poprawną kategorię/rolę → `422`).
  - Rozszerzenie `GET /api/audits/{audit_id}`: `decision` na `AuditClaimResponse`, `decision_status`, `decisions_count` oraz `history` na `AuditDetailResponse`. Po zmianie kontraktu wymagana jest synchronizacja `backend/openapi.json` i `frontend/app/api/schema.d.ts` (`AGENTS.md`).
- **Obserwowalność i przepływ danych:**
  - `backend/app/observability.py:1-105` obsługuje wyłącznie przebiegi LangGraph/LangChain i jawnie wyklucza dane sesji ze śladów (`:83,98-99`).
  - `backend/app/auditing/runner.py:1-236` uruchamia graf audytu i wywołuje `store.complete_audit` (`:192`) oraz `store.fail_audit` (`:56`), więc nie wymaga bezpośrednich zmian, jeśli zdarzenia historii są zapisywane w `store.py`.
  - Decyzje redaktora i wpisane uzasadnienie pozostają wyłącznie w ParadeDB — nie są wysyłane do dostawcy LLM ani do Langfuse Cloud.

### 2. Frontend: makiety (`3`, `3N`, `3N-D`), obecny kod S-08 i dostępność

- **Pliki makiet na kanwie (`design/mockups/canvas/canvas.json:48-54,83-89,104-110`):**
  - Ekran `3` (desktop `1440x900`): `design/mockups/canvas/S3.dc.html`
  - Ekran `3N` (wąskie okno `390x1640`): `design/mockups/canvas/S3N.dc.html`
  - Ekran `3N-D` (arkusz decyzji `390x844`): `design/mockups/canvas/S3ND.dc.html`
  - (Warianty ciemne `S3Dark.dc.html`, `S3NDark.dc.html` pominięte — `FR-022` jest poza MVP.)
- **Układ desktopowy `S3.dc.html:26`:**
  - 3 obszary w poziomie pod `AppHeader`: szyna nawigacji (`56 px`), główny obszar (lewa kolumna `440 px` z notatką i listą tez + środkowa kolumna oceny systemu z dolnymi akordeonami `<details>` `Historia` i `Jak powstała ta analiza`) oraz stały prawy panel `<aside aria-label="Decyzja redaktora">` (`340 px`, tło `#f4f2ec`, lewa krawędź `#e9e7e0`).
- **Układ wąski `390 px` (`S3N.dc.html:26`, `S3ND.dc.html:26`):**
  - Jednokolumnowy przepływ z dolnym paddingiem pod przyklejony pasek (`padding-bottom: 110px`).
  - Przyklejony dolny pasek CTA z przyciskiem `height: 48px`, `background: #2f5fc4`: po lewej ikona osoby + `Decyzja dla T{n}`, po prawej status (`nie zapisano` / zapisana) + szewron. *(Podpis „Pasek przyklejony do dołu okna” w `S3N.dc.html:26` to adnotacja makiety, nie element interfejsu.)*
  - Kliknięcie otwiera arkusz `3N-D` (`role="dialog"`, tło `#f4f2ec`, `border-radius: 16px 16px 0 0`, uchwyt `40x4px`, tło przysłony `rgba(31,32,35,.4)`, przycisk zamknięcia `40x40px`, dodatkowy wiersz kontekstu z badge `T{n}` + etykietą tezy oraz podtytułem z oceną systemu).
- **Formularz decyzji (`S3.dc.html:26`, `S3ND.dc.html:26`, `prd.md:109-110`):**
  - 4 kategorie w `<div role="radiogroup" aria-label="Decyzja">`, dokładnie w tej kolejności:
    1. `Zgoda z oceną systemu`
    2. `Poproś o źródło lub zweryfikuj`
    3. `Rozważ uzupełnienie dokumentacji`
    4. `Ocena systemu błędna`
  - **Brak domyślnego wyboru**, pod spodem tekst pomocniczy `Nic nie jest wybrane z góry.`
  - Pole `Uzasadnienie (wymagane)` (`<textarea rows="4">`, placeholder `Napisz, dlaczego tak decydujesz`).
  - Przycisk zapisu w stanie nieaktywnym: `Wybierz decyzję i wpisz uzasadnienie` (`#e8e5dc` / `#55595f`).
  - Zastrzeżenie pod przyciskiem: `Zapis nie zmienia ani nie publikuje dokumentacji. Rola „Redaktor” bez weryfikacji tożsamości.`
- **Sekcja `Historia` (`S3.dc.html:26`, `S3N.dc.html:26`):**
  - Zwinięty `<details>` umieszczony bezpośrednio nad `Jak powstała ta analiza` na dole środkowej kolumny. W makiecie ma placeholder (`Przykładowa oś zdarzeń.`), więc rzeczywisty układ wpisów definiuje PRD (`prd.md:111,183,221`): faktyczne zdarzenia w kolejności chronologicznej z wyraźnym rozróżnieniem zdarzeń systemu (`SystemIcon`) i decyzji człowieka (`PersonIcon`).
- **Istniejący kod S-08 do wykorzystania:**
  - `frontend/app/routes/audit-detail.tsx:31-192`: odpytuje `fetchAudit(id)` co `1500 ms` podczas `queued`/`running`; po `completed` renderuje `<AuditResultView audit={audit} />` (`:191`). Wymaga przekazania callbacku aktualizacji stanu (np. `onAuditChange`) po zapisie decyzji.
  - `frontend/app/components/audit/AuditResultView.tsx:152-692`: renderuje lewą i środkową kolumnę, obsługuje `Escape` (`:181-191`), przywracanie fokusu (`:168-179`) i prawy slot `sidePanel` dla `CaseContextPanel` / `EvidencePanel` (`:239-335,:522`).
  - `frontend/app/components/assistant/PanelFrame.tsx:25-115`: na `< 768 px` renderuje `PanelSheet` oparty na natywnym `<dialog>.showModal()` z trapem fokusu, przysłoną `rgba(31,32,35,.4)`, `onCancel`, zamykaniem kliknięciem w tło i zerowym przewijaniem poziomym przy `390 px` (`:102`). Można go bezpośrednio wykorzystać (lub wydzielić wariant) dla `3N-D`.
  - `frontend/app/session/role.tsx:12-44`: `useRole()` zwraca `{ role, setRole }` (`"consultant" | "editor"`, domyślnie `"consultant"`, zapis w `localStorage` pod `kops.role`).
  - `frontend/app/app.css:4-47`: wszystkie tokeny kolorystyczne ekranu `3`/`3N`/`3N-D` są już zdefiniowane (`--color-surface-alt`, `--color-nav-active`, `--color-chip-text`, `--color-border`, `--color-subtle`, `--color-primary`, `--color-success`, `--color-supported-bg`, `--color-claim-selected`).
  - `frontend/app/components/assistant/Icon.tsx`: posiada ikony statusów i `SystemIcon`, brakuje jedynie `PersonIcon` dla nagłówka decyzji i dolnego przycisku `3N`.
  - `frontend/app/i18n/pl.ts` i `en.ts`: `en.ts` jest typowane jako `Record<TranslationKey, string>`, więc `tsc` pilnuje kompletności obu języków.

### 3. Wzorce z AI Devs 4 (`04_05_review`)

- **Do adaptacji (Python/FastAPI + React SPA):**
  - Deterministyczne sortowanie elementów i opcjonalne przejście do kolejnej nierozstrzygniętej tezy przy zachowaniu stabilnego zaznaczenia przy edycji istniejącej decyzji (`state.svelte.js:119-142,212-223,297-322`).
  - Blokowanie mutacji podczas trwania analizy lub zapisu w locie (`keys.js:73`, `CommentTooltip.svelte:36`, `StatusBar.svelte:8`).
  - Ochrona skrótów klawiszowych przed polami edycyjnymi `isEditableTarget()` (`keys.js:4-12,35`) — istotna przy polu `<textarea>` uzasadnienia.
  - Autorytatywny zwrot zaktualizowanego stanu z backendu po walidacji przejścia (`review-engine.js:424-452`, `api.js:214,230`).
  - Liczniki postępu wyliczane ze zbioru elementów (`state.svelte.js:156-160`, `StatusBar.svelte:30-36`), u nas zawsze z tekstem i ikoną.
- **Bezwzględnie wykluczone (naruszałyby twarde zasady MVP):**
  - Jakiekolwiek patchowanie lub zapisywanie plików dokumentacji (`review-engine.js:470-537,566-621,697-707`, `store.js:162-173`, `server.js:201-213,243-248`).
  - Cofanie zmian w tekście dokumentu (`review-engine.js:539-564`) oraz widok diffa `- old / + new` i sugestii zamiany tekstu (`CommentTooltip.svelte:113-157`, `tools.js:28-50`).
  - Wywoływanie LLM po zapisie decyzji (`review-engine.js:216-252,668-675`) i przechowywanie stanu w plikach JSON (`store.js:213-224`).

### 4. Rozbieżności między makietami, PRD, dokumentacją historyczną a kodem S-08

| Źródło / twierdzenie | Stan względem aktualnego kodu i PRD | Wpływ na S-09 |
|---|---|---|
| `architecture-notes.md:30` — historia `FR-021` z checkpointu LangGraph w Postgresie | **Sprzeczne z kodem S-08** (`0004_audits.sql`, `main.py:39`, `store.py:255-271`): S-08 przechowuje stan w `audits`/`audit_claims` bez checkpointów LangGraph. | `FR-021` realizujemy przez dedykowaną tabelę SQL `audit_events`, nie przez checkpointy LangGraph. |
| `S3.dc.html:26`, `S3N.dc.html:26` — linia `Sugestia systemu: poproś o źródło lub zweryfikuj. To tylko wskazówka, nie wybór.` | **Nieobecne w PRD** (`prd.md:109-110,221`) ani w danych S-08 (`AuditResultView.tsx:527-692`). | Decyzja produktowa dla planu: pominąć linię sugestii (zalecane, aby nie podpowiadać decyzji) albo jawnie zdefiniować jej regułę. |
| `S3.dc.html:26` — podsumowanie historii `3 zdarzenia · ostatnie: szkic` | **Częściowo sprzeczne z PRD** (`prd.md:109,111,183`): PRD nie definiuje stanu „szkic” i wymaga wyłącznie rzeczywistych zdarzeń. | Pokazywać wyłącznie rzeczywistą liczbę i typ ostatniego zapisanego zdarzenia z `audit_events`. |
| `S3.dc.html:26`, `S3N.dc.html:26`, `S3ND.dc.html:26` — brak wskaźnika postępu decyzji (`X/N` / `zapisana`) | **Wymagane w PRD/roadmapie** (`prd.md:109`, `roadmap.md:346`), obecne dopiero na makiecie listy `S5.dc.html:26` (`2 z 2 tez rozstrzygnięte`, `Zapisane`). | Dodać wskaźnik decyzji na elementach listy `Tezy z notatki` (słowo + ikona) oraz zbiorczy status postępu/zapisu analizy w `AuditResultView`. |
| `S3.dc.html:26` (`Analizy / SIM-P04`) i `S3N.dc.html:26` (`Wróć do listy analiz`) | **Odłożone do S-10** (`context/archive/2026-11-26-resolved-case-audit/plan.md:41`): trasa `/analizy` jeszcze nie istnieje. | Zachować link do `/audyt` (`AuditResultView.tsx:344-349`); nie dodawać martwych linków przed S-10. |
| `docs/przeplyw-danych.md:1,3,38` — nagłówek `(stan po S-02)` i sekcja retencji `Dotyczy tabeli answers.` | **Częściowo nieaktualne** (sekcja S-08 jest obecna w `:19-29`, ale nagłówek `:1,3` i sekcja retencji `:38` nie zostały zaktualizowane). | W S-09 dopisać tabelę decyzji i zdarzeń historii do `docs/przeplyw-danych.md` (plik lokalny w `.gitignore`, bez `git add -f`) oraz zaktualizować listę tabel w sekcji retencji. |

---

## Code References

- `backend/migrations/0004_audits.sql:1-63` — obecny schemat `audits` i `audit_claims` (bez FK do tabel migawki).
- `backend/app/migrations.py:39-61` — weryfikacja SHA-256 zastosowanych migracji (wymusza addytywne `0005_*.sql`).
- `backend/app/auditing/store.py:93-126,161-271,274-313` — transakcje cyklu życia audytu (`create_audit`, `complete_audit`, `fail_audit`, `fail_orphaned_audits`) i odczyt `get_audit_for_session`.
- `backend/app/api/audits.py:38-113,167-265` — obecne schematy Pydantic i endpointy `POST /api/audits`, `GET /api/audits/{audit_id}`.
- `backend/app/session.py:31-71` — `SessionDep` (tworzy ciasteczko `kops_session`) oraz `AuditSessionDep` (`404` bez sesji).
- `backend/app/observability.py:83,98-99` — izolacja danych sesji od śladów Langfuse.
- `backend/app/db.py:25` — limit puli połączeń (`max_size=5`).
- `frontend/app/routes/audit-detail.tsx:31-192` — polling i przejście do `AuditResultView`.
- `frontend/app/components/audit/AuditResultView.tsx:152-692` — układ ekranu `3`/`3N`, slot `sidePanel`, `Escape` i przywracanie fokusu.
- `frontend/app/components/assistant/PanelFrame.tsx:25-115` — przełączanie desktop `<aside>` / mobile `<dialog>.showModal()` przy `768 px`.
- `frontend/app/session/role.tsx:12-44` — stan roli (`consultant` / `editor`) w `localStorage`.
- `frontend/app/components/assistant/Icon.tsx` — ikony statusów i `SystemIcon` (brakuje `PersonIcon`).
- `frontend/app/api/audits.ts:1-43` — klient HTTP audytu oparty na wygenerowanym `schema.d.ts`.
- `design/mockups/canvas/S3.dc.html:26`, `S3N.dc.html:26`, `S3ND.dc.html:26`, `S5.dc.html:26` — wzorce struktury, tekstów i stylów.

---

## Architecture Insights

- **Spójność danych bez LLM w ścieżce decyzji:** Zapis decyzji to czysta, krótka transakcja SQL (`UPSERT` w `audit_claim_decisions` + `INSERT` w `audit_events`) zwracająca zaktualizowany stan decyzji i zdarzenie historii (albo pełny szczegół audytu), bez wpływu na limit równoległych grafów (`AuditTaskManager`) ani na Langfuse.
- **Koordynacja paneli bocznych na desktopie (`1280 px` vs `1440 px`):** W S-08 `EvidencePanel` i `CaseContextPanel` współdzielą prawy slot `PanelFrame` (otwarcie jednego zamyka drugi). W S-09 na desktopie dochodzi stały prawy panel decyzji (`340 px`). Aby uniknąć ścisku/przewijania na `1280 px`, otwarcie `EvidencePanel` lub `CaseContextPanel` powinno tymczasowo zastępować prawy panel (z powrotem do panelu decyzji po zamknięciu) lub przyjmować breakpoint `lg`/`xl` (do doprecyzowania w planie).
- **Współdzielenie `PanelSheet` dla `3N-D`:** `PanelFrame` (`<dialog>.showModal()`) spełnia już wymagania dostępności arkusza z `S3ND.dc.html` (trap fokusu, przysłona, `Escape`, brak poziomego przewijania przy `390 px`), a w `audit-new.tsx` ustalono wzorzec anulowania żądań przez `AbortController` przy odmontowaniu.

---

## Historical Context (from prior changes)

- `context/archive/2026-11-26-resolved-case-audit/plan.md:5,40-42` — jawne odłożenie panelu decyzji, 4 kategorii, `S3N-D` i `Historia` (`FR-009`, `FR-021`) do S-09, a listy analiz (`FR-010`) do S-10.
- `context/archive/2026-11-26-resolved-case-audit/plan.md:51,73-75` — celowe przygotowanie stabilnych UUID (`audits.id`, `audit_claims.id`, `is_demo`, `case_ref`) w `0004_audits.sql` pod `0005_*.sql`.
- `context/archive/2026-11-26-resolved-case-audit/reviews/impl-review.md:25-37,83-111` — zaakceptowane reguły z przeglądu S-08: (F1) brak surowych wyjątków w API/UI, (F6) `GET /api/audits/{id}` fail-closed na `AuditSessionDep` (obsługa `is_demo` bez ciasteczka odłożona do S-10), (F7) `AbortController` na mutacjach, (F8) dostępność klawiaturowa podświetleń tez.

## Related Research

- `context/archive/2026-11-26-resolved-case-audit/research.md` — badanie S-08 (schemat audytu, graf, makiety `2`/`2P`/`3`/`3N`).

## Open Questions (do rozstrzygnięcia w `/10x-plan`)

1. **Zachowanie formularza decyzji w roli `consultant` (`FR-011`, `prd.md:237,241-245`):** Czy przy roli `consultant` formularz jest tylko do odczytu z przyciskiem „Przełącz na rolę Redaktor” (z wyraźnym zaznaczeniem, że to nie kontrola dostępu), czy aktywny z zapisem `role_label = "consultant"` i jawną informacją o aktywnej roli?
2. **Linia „Sugestia systemu” z makiety `S3`/`S3N`:** Pominąć (zgodnie z PRD, bez podpowiadania wyboru redaktorowi) czy dodać jako opcjonalny, niemutowalny opis?
3. **Edycja zapisanej decyzji:** Czy redaktor może zmienić już zapisaną decyzję dla tezy (wtedy `PUT` robi `UPSERT` w `audit_claim_decisions` i dopisuje `decision_updated` w `audit_events`), czy decyzja jest jednorazowa?
4. **Klucz unikalności decyzji przy przyszłych `is_demo = true` (S-10):** Czy w `0005_*.sql` od razu dodać `session_hash` do `audit_claim_decisions` i `UNIQUE (claim_id, session_hash)` (albo zablokować zapis decyzji na `is_demo = true` lub izolować per sesja), aby S-10 nie musiało zmieniać klucza unikalności?
5. **Współistnienie panelu decyzji z `EvidencePanel` / `CaseContextPanel` na `1280 px`:** Czy otwarcie dowodu / kontekstu sprawy na desktopie tymczasowo zastępuje prawy panel decyzji (i przywraca go po `Escape` / `X`), oraz przy jakim breakpoincie (`lg: 1024 px` czy `xl: 1280 px`) panel decyzji przechodzi w dolny pasek + arkusz `3N-D`?
6. **Edge case `claims_total == 0` oraz backfill `audit_events`:** Jaki `decision_status` ma ukończony audyt bez wyodrębnionych tez (nie powinien być `saved`) i czy `0005_*.sql` ma wygenerować początkowe zdarzenia `audit_created`/`evaluation_completed`/`evaluation_failed` dla audytów już obecnych w bazie?
