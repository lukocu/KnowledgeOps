# Odpowiedź z cytatami albo abstencja (S-02) — Plan Brief

> Full plan: `context/changes/grounded-answer-or-abstention/plan.md`

## What & Why

Konsultant zadaje pytanie po angielsku i dostaje jeden z dwóch wyników:
- odpowiedź złożoną wyłącznie z tez, które popiera cytowany fragment migawki TechQA;
- jawną abstencję z listą sprawdzonych fragmentów.

To gwiazda przewodnia roadmapy: pierwszy etap, który pokazuje regułę produktu w działaniu. Ta sama ocena tezy posłuży później audytowi (S-08).

## Starting Point

S-01 zostawiło migawkę w ParadeDB: 28 481 dokumentów, 105 450 fragmentów z offsetami i indeks BM25. TRAIN_Q000 trafia w `swg21996508` na pozycji 1.

Brakuje warstw nad tym:
- backend ma tylko `/api/health`, bez LangChain, LangGraph, Langfuse i SDK modelu;
- frontend to ekran powitalny szablonu bez i18n.

## Desired End State

Konsultant otwiera aplikację z powłoką z kanwy (role, DEMO, PL/EN domyślnie PL, migawka) i zadaje pytanie. Widzi kroki postępu z rzeczywistych etapów grafu, a potem jeden z ekranów:
- **1A:** odpowiedź z numerami cytatów i panelem dowodu (fragment, rozwijane sąsiedztwo, cały dokument);
- **1C:** abstencję z wyjaśnieniem i sprawdzonymi fragmentami.

Odpowiedź żyje pod `/odpowiedz/:id` w anonimowej sesji. Każde zapytanie ma ślad w Langfuse Cloud.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Dostawca modelu czatu | OpenAI przez `langchain-openai`, model w `.env` | Jeden dostawca także dla embeddingów w S-04, strict structured output. |
| Ocena tezy | Szkic z cytatami → test dosłowności w kodzie → osobny weryfikator (supported / contradicted / insufficient) | Werdykt jest osobnym, testowalnym krokiem, wielokrotnego użytku w S-08 i mierzalnym w S-06. |
| Częściowe wsparcie | Odpowiedź tylko z tez `supported`, liczba pominiętych w szczegółach; abstencja, gdy żadna nie jest poparta | Zgodne z Business Logic i ogranicza nadmierną abstencję. |
| Wyszukiwanie | Pytanie wprost do BM25, k=8 | Bez dodatkowego wywołania modelu; alternatywy zmierzą S-04 i S-13. |
| Teza sprzeczna | Pomijana jak niepoparta | Pokazywanie obu stron należy do S-07. |
| Postęp | SSE na `POST /api/answers` z etapów grafu (`get_stream_writer`) | `fastapi.sse` jest w FastAPI 0.165, a UI pokazuje tylko rzeczywiste etapy. |
| Ślad | Langfuse Cloud, no-op bez kluczy | Decyzja użytkownika; odstępstwo od architecture-notes trafia do notatek. |
| Zapis odpowiedzi | Tabela `answers` bez kluczy obcych do migawki | Odświeżenie i link działają, a reimport nie kasuje odpowiedzi kaskadowo. |
| Dostęp do odpowiedzi | Tylko ta sama sesja (ciasteczko `HttpOnly`, w bazie hash); inna sesja dostaje 404 | Zgodne z PRD Access Control i gotowe pod S-08. |
| Front a S-03 | S-02 wchłania S-03 (role, PL/EN, DEMO), domyślnie polski | Jedno źródło powłoki; S-03 zamykany razem z S-02. |
| Kompletność tłumaczeń | `en: Record<keyof typeof pl, string>` sprawdzane przez `tsc` | Bez nowego frameworka (AGENTS.md). |
| Znacznik przy kodzie | Numer przed blokiem kodu | Numer jest przy zdaniu, a kopiowanie kodu nie łapie numeru. |
| Model cytatu | Jeden numer na fragment z listą tez i offsetami cytatów; panel zaznacza cytat w `<mark>` | Zgodne z S1A: dowód pokazuje dokładnie zweryfikowane zdanie. |
| Kontrola abstencji | Najpierw przeszukać korpus pod Q002; gdy są trafienia, użyć pytania z makiety 1C | Etykieta `is_impossible` dla Q002 nie jest zweryfikowana. |
| Testy | Fałszywy model w CI oraz marker `live` z prawdziwym OpenAI uruchamiany ręcznie | Deterministyczne CI i realna kontrola na żądanie. |

## Scope

**In scope:**
- asynchroniczne BM25, okno dowodu i cały dokument, `GET /api/corpus`;
- graf LangGraph, prompty i schematy, ślad Langfuse;
- tabela `answers`, sesja, SSE i odczyt po id;
- powłoka z S-03;
- ekrany 1P, 1A i 1C oraz stan błędu;
- opis przepływu danych.

**Out of scope:**
- kopiowanie odpowiedzi i 390 px (S-05);
- sprzeczne źródła (S-07);
- wektory i hybryda (S-04), przepisywanie zapytań i reranking;
- cache (S-14);
- pomiar abstencji (S-06);
- retencja sesji;
- linki do ekranów audytu i listy analiz;
- lokalny Langfuse, ciemny motyw, Playwright.

## Architecture / Approach

`POST /api/answers` uruchamia graf `retrieve (BM25, k=8) → draft (tezy z chunk_id i dosłownym cytatem) → quote_check (kod) → verify (werdykt dla każdej tezy) → compose | abstain`. Każdy węzeł emituje zdarzenie etapu, które endpoint przekazuje jako SSE.

Po zakończeniu grafu wynik trafia do `answers`, a klient dostaje `result` z `answer_id` i przechodzi na `/odpowiedz/:id`. Panel dowodu pobiera `GET /api/evidence`, czyli okno `documents.text` od poprzedniego do następnego fragmentu z zaznaczonymi offsetami, a na żądanie `GET /api/documents`. LangChain służy tylko do modelu i wyjścia ustrukturyzowanego, a SQL wyszukiwania pozostaje ręczny.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Wyszukiwanie i API dowodu | Async BM25, okno i dokument, `/api/corpus`, wybrane pytanie kontrolne abstencji | Q002 może mieć odpowiedź w korpusie (wtedy pytanie z 1C) |
| 2. Graf odpowiedzi | Graf z regułą odpowiedzi, prompty, fałszywy model, `live`, ślad | Jakość weryfikatora i czas dwóch wywołań wobec p95 < 10 s |
| 3. API odpowiedzi i sesja | SSE, `answers`, ciasteczko sesji, odczyt, kontrakt OpenAPI | Typy zdarzeń SSE w OpenAPI wymagają jawnych schematów |
| 4. Powłoka (S-03) | Tokeny, nagłówek, role, PL/EN, nawigacja | Rozrost etapu przez zakres S-03 |
| 5. Ekrany 1P, 1A i 1C | Postęp, odpowiedź z panelem dowodu, abstencja, stan błędu | Klawiatura i fokus w panelu dowodu |
| 6. Weryfikacja i dokumentacja | Przebieg live, ślad, porównanie z kanwą, przepływ danych, notatki | Akceptacja wizualna zależy od użytkownika |

**Prerequisites:**
- pełna migawka zaimportowana (S-01);
- klucz OpenAI;
- projekt i klucze Langfuse Cloud w `.env`.

**Estimated effort:** ~5–7 sesji implementacyjnych w 6 fazach; najcięższe są fazy 2 i 5.

## Open Risks & Assumptions

- Dwa wywołania modelu mogą zbliżyć się do 10 s. `chat_timeout_s` (12 s na wywołanie) i `answer_deadline_s` (25 s na zapytanie) zapobiegają wiszeniu, a p95 zmierzy S-06.
- Pytanie kontrolne abstencji: Faza 1 sprawdza w korpusie Q002 i pytanie z 1C. Gdy oba mają odpowiedź w korpusie, użytkownik wskazuje inne.
- Weryfikator może być zbyt surowy (nadmierna abstencja) albo zbyt łagodny. Jakość zmierzy S-06 na oznaczonym zestawie, tu są tylko kontrole działania.
- Dane odwiedzającego (pytania, fragmenty) trafiają do OpenAI i Langfuse Cloud, a retencja jest nierozstrzygnięta. To blokuje publiczne demo, nie ten etap.
- Nazwę modelu ustala implementujący z bieżącej oferty OpenAI (mały model ze strict structured output).

## Success Criteria (Summary)

- TRAIN_Q000 daje w interfejsie odpowiedź z cytatem do `swg21996508`, który otwiera się w panelu dowodu z sąsiedztwem i całym dokumentem.
- Pytanie kontrolne abstencji daje ekran 1C z wyjaśnieniem i listą sprawdzonych fragmentów.
- Każde zapytanie ma ślad w Langfuse Cloud z etapami i identyfikatorami fragmentów, CI jest zielone, a zrzuty zaakceptowano wobec kanwy.
