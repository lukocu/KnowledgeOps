---
project: "KnowledgeOps Assistant"
version: 1
status: draft
created: 2026-11-22
context_type: greenfield
product_type: web-app
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 8
  hard_deadline: null
  after_hours_only: false
---

# KnowledgeOps Assistant — PRD

Źródła: `context/foundation/shape-notes.md` (główne źródło wymagań), `design/mockups/README.md` i kanwa Claude Design (wizualne przedstawienie przepływów) oraz decyzje użytkownika z 22.11.2026, które rozstrzygnęły rozbieżności między makietami a shape-notes (oznaczone „Decyzja 2026-11-22”). Makiety ilustrują przepływy. Dane, liczby, czasy i oceny widoczne na makietach są przykładowe i nie są wymaganiami ani wynikami systemu.

## Vision & Problem Statement

Konsultant technicznego help desku, obsługując zgłoszenie dotyczące produktu informatycznego, musi znaleźć instrukcję pasującą do problemu i ocenić, czy może na niej polegać (czy dowód dotyczy tej tezy, produktu i wersji). Wiedza jest rozproszona po instrukcjach, bazie wiedzy i innych dokumentach; ręczne wyszukiwanie i ręczne przeglądy są czasochłonne. Wiedza z rozwiązanych zgłoszeń nie wraca do bazy — właściciel/redaktor wiedzy nie ma konkretnych sygnałów, które materiały są niepełne, potencjalnie nieaktualne lub sprzeczne. Kategorie bólu: zaufanie/paraliż decyzyjny, wiedza rozproszona, narzut koordynacyjny, tarcie w workflow. Koszt nie jest zmierzony: problem ma wstępne potwierdzenie w małym, niereprezentatywnym badaniu (12 doświadczeń) oraz analogię w opisie Microsoft Global Help Desk; produkt nie twierdzi, że obniża koszty ani że jest poszukiwany przez konkretną firmę.

Insight: zwykła wyszukiwarka lub chatbot RAG nie rozwiązuje problemu zaufania. KnowledgeOps Assistant (1) odpowiada wyłącznie na podstawie dowodów i jawnie wstrzymuje się, gdy dowodów brakuje; (2) każdą tezę prowadzi do konkretnego fragmentu, dokumentu i migawki; (3) traktuje rozwiązane zgłoszenie jako sygnał do porównania z dokumentacją — ale rozwiązanie nie jest automatycznie prawdą, a brak wyniku nie dowodzi luki — decyzję zawsze podejmuje człowiek; (4) każdy element (retrieval, cytaty, abstencja, audyt) jest mierzony na oznaczonych danych, a wyniki są raportowane z liczebnością próby, bez wymyślonych wartości.

Kontekst projektu: projekt portfolio na publicznych danych (NVIDIA TechQA-RAG-Eval, pytania z forów IBM jako symulowane zgłoszenia). Scenariusz biznesowy i wpływ na pracę są hipotezami; biznesowe miary (czas rozwiązania, eskalacje) wymagają osobnego badania z prawdziwym zespołem.

## User & Persona

### Primary persona — Konsultant help desku

Konsultant technicznego wsparcia produktu informatycznego (hipotetyczna firma technologiczna). Sięga po produkt w trakcie obsługi zgłoszenia: wpisuje pytanie lub opis problemu, porównuje dowody i decyduje, jak odpowiedzieć. Po rozwiązaniu sprawy może przekazać rozwiązanie do analizy (w pierwszej wersji ręcznie).

### Secondary persona — Właściciel / redaktor wiedzy

Przegląda sygnały z analizy rozwiązanych zgłoszeń (możliwe uzupełnienie, możliwa sprzeczność, niewystarczające dowody), sprawdza fragmenty zgłoszenia i dokumentów oraz zapisuje decyzję z uzasadnieniem. Role opisują zadania i mogą należeć do tej samej osoby — podział jest hipotezą do weryfikacji.

> Socrates (faza 1): „Dlaczego istniejące narzędzia AI search w helpdesku tego nie załatwiają?” — Odpowiedź: to projekt portfolio, nie produkt konkurujący na rynku. Celem jest pokazanie mierzalnego, ugruntowanego RAG-a z audytem wiedzy; przewaga rynkowa nie jest tezą projektu.

## Success Criteria

### Primary

- Oba przepływy działają end-to-end: (a) pytanie → odpowiedź z cytatami lub abstencja; (b) rozwiązane zgłoszenie → oceny tez z dowodami → zapisana decyzja redaktora.
- Wyszukiwanie hybrydowe osiąga wyższy Recall@k (poziom dokumentu) niż wyszukiwanie leksykalne na zweryfikowanych pytaniach TechQA. Próg liczbowy: ustalany po zmierzeniu baseline leksykalnego i zamrażany przed końcowym testem (patrz Open Questions, pozycja 1).
- Opublikowane wyniki trzech sprawdzianów (1: wyszukiwanie i odpowiedzi; 2: brak dowodów i sprzeczności; 3: audyt rozwiązanych zgłoszeń i review) z liczebnością próby i ograniczeniami.
- Audyt: zgodność kategorii z ręcznymi etykietami na niezależnym zestawie powyżej progu ustalonego na zestawie deweloperskim (pilotaż) i zamrożonego przed testem niezależnym (patrz Open Questions, pozycja 1).

### Secondary

- Ślad każdego zapytania dostępny dla operatora (etapy, identyfikatory pobranych fragmentów, wersje promptów, czas, koszt, błędy).
- Eksperyment z cache (brak / dokładny / semantyczny) z wynikami: trafienia, błędne ponowne użycia, czas, koszt.
- Porównanie strategii chunkingu (recall, jakość cytatów, tokeny, koszt).
- Porównanie z rerankingiem (jakość vs opóźnienie i cena).

### Guardrails

- Brak odpowiedzi bez dowodu: każda istotna teza odpowiedzi ma cytat z dostępnego fragmentu bazy; w przeciwnym razie system wstrzymuje się i komunikuje brak wystarczających dowodów.
- Dane w publicznym demo (Decyzja 2026-11-22): przed wpisaniem treści odwiedzający widzi informację, aby nie wklejać danych osobowych ani poufnych. Analizy utworzone przez odwiedzającego nie są widoczne dla innych odwiedzających. Dane sesji są przechowywane przez ograniczony czas, a potem usuwane (okres: patrz Open Questions, pozycja 10).
- Informacje o sposobie przygotowania odpowiedzi lub analizy pokazują wyłącznie rzeczywiste dane; produkt nigdy nie przedstawia przykładowych czasów ani wyników jako prawdziwych.

## User Stories

Przepływ MVP (z shape-notes) i ekrany, które go ilustrują na kanwie Claude Design:

| Krok przepływu | Ekran na kanwie |
|---|---|
| 1. Konsultant otwiera aplikację i wpisuje pytanie / opis zgłoszenia. | 1A, 1P (stan postępu) |
| 2. Widzi odpowiedź z cytatami (dokument, fragment, migawka) albo komunikat o braku wystarczających dowodów. | 1A, 1C, 4 (różne zalecenia źródeł) |
| 3. Otwiera cytat i porównuje go z fragmentem źródła. | 1A (panel dowodu), 1N (wąskie okno) |
| 4. Po rozwiązaniu sprawy wkleja opis zgłoszenia i notatkę z rozwiązaniem (ręcznie). | 2, 2P (stan postępu) |
| 5. System wyodrębnia tezy i ocenia każdą — z fragmentami zgłoszenia i dokumentów. | 3, 3N |
| 6. Przełączenie na rolę redaktora → przegląd dowodów → zapis decyzji z uzasadnieniem dla każdej tezy. | 3, 3N-D, 5 (lista analiz) |

Makiety pokazują układ i zachowanie, nie wyniki systemu. Przykład P04 w ekranach 3/3N jest syntetyczny, dokument B w ekranie 4 jest syntetyczny, a oceny w ekranie 5 to etykiety z pilotażu. Pytania i odpowiedzi na makietach są po polsku, ale w MVP są po angielsku (FR-018); polskie teksty makiet są punktem wyjścia do tłumaczeń interfejsu.

### US-01: Konsultant dostaje odpowiedź ze źródłami albo informację o braku dowodów

- **Given** konsultant w roli konsultanta i zaindeksowana migawka bazy wiedzy
- **When** wpisuje pytanie dotyczące zgłoszenia
- **Then** widzi odpowiedź, w której każda istotna teza ma cytat (dokument, fragment, migawka), albo jawny komunikat o braku wystarczających dowodów

#### Acceptance Criteria

- Cytat wspiera konkretną tezę, a nie tylko dotyczy podobnego tematu.
- Kliknięcie cytatu pokazuje fragment w kontekście dokumentu źródłowego.
- Przy niewystarczającym materiale system nie generuje odpowiedzi „na pamięć” — komunikuje brak dowodów.
- Komunikat o braku dowodów wyjaśnia, że brak dowodów nie oznacza odpowiedzi „nie” ani tego, że informacji nie ma w całej bazie, oraz pokazuje listę sprawdzonych fragmentów. (Decyzja 2026-11-22)
- Skopiowana odpowiedź zachowuje powiązanie każdej tezy z jej źródłem; skopiowany tekst zawiera co najmniej numer cytatu i identyfikator dokumentu. (Decyzja 2026-11-22)
- Szczegóły przygotowania odpowiedzi pokazują rzeczywiste informacje, w tym migawkę i zakres wyszukiwania. (Decyzja 2026-11-22)

Ilustracja: 1A (odpowiedź z cytatami i dowodem), 1C (brak wystarczających dowodów), 1N (wąskie okno).

### US-02: Analiza rozwiązanego zgłoszenia i decyzja redaktora

- **Given** konsultant rozwiązał sprawę i ma opis zgłoszenia oraz notatkę z rozwiązaniem
- **When** przekazuje je ręcznie do analizy, a następnie (w roli redaktora) otwiera wynik
- **Then** widzi wyodrębnione tezy, ocenę każdej tezy (poparta / sprzeczna / niewystarczające dowody) i ocenę całej notatki (pełne pokrycie / częściowe pokrycie / sprzeczność / niewystarczające dowody) z fragmentami zgłoszenia i dokumentów, i zapisuje decyzję z uzasadnieniem dla każdej tezy

#### Acceptance Criteria

- Każda teza jest oceniana osobno przed oceną całej notatki.
- Brak wyniku wyszukiwania jest prezentowany jako „niewystarczające dowody”, nie jako dowód luki w całej bazie; treść zgłoszenia nie jest traktowana jako prawda.
- Brak dowodu nie jest prezentowany jako sprzeczność.
- Zapis decyzji nie zmienia ani nie publikuje dokumentacji.
- Dowody dla tez są szukane w całej migawce bazy wiedzy; wynik zawsze pokazuje, jaki zakres sprawdzono. (Decyzja 2026-11-22)
- Redaktor zapisuje decyzję i uzasadnienie dla każdej tezy, także popartej; analiza ma status „zapisana”, gdy wszystkie tezy mają decyzję. Uzasadnienie jest wymagane. (Decyzja 2026-11-22)
- Decyzja jest wybierana z listy: „Zgoda z oceną systemu”, „Poproś o źródło lub zweryfikuj”, „Rozważ uzupełnienie dokumentacji”, „Ocena systemu błędna”. Żadna opcja nie jest wybrana z góry. Lista jest startowa i zostanie potwierdzona po pilotażu decyzji. (Decyzja 2026-11-22)
- Historia analizy pokazuje faktyczne zdarzenia, w tym utworzenie analizy, wynik oceny systemu i zapis decyzji człowieka; decyzja jest zawsze odróżniona od oceny systemu. (Decyzja 2026-11-22)
- Szczegóły przygotowania analizy pokazują rzeczywiste informacje, w tym migawkę i zakres wyszukiwania. (Decyzja 2026-11-22)

Ilustracja: 2 (przekazanie), 3 i 3N (ocena tez i decyzja), 3N-D (decyzja w wąskim oknie).

### US-03: Sprzeczne źródła

- **Given** pytanie, na które materiały w bazie odpowiadają w sposób wykluczający się
- **When** konsultant zadaje to pytanie
- **Then** system nie wybiera po cichu jednej wersji — pokazuje obie instrukcje i ich źródła, z datą lub wersją, jeśli są znane

#### Acceptance Criteria

- Obie strony mają cytaty i identyfikatory dokumentów.
- Jeśli sprzeczności nie da się rozstrzygnąć na podstawie dostępnych danych, system mówi to wprost.
- Stan jest nazwany „sprzecznością” tylko wtedy, gdy oba dokumenty dotyczą tego samego zakresu (produkt, wersja, kontekst). W pozostałych przypadkach jest nazwany neutralnie („różne zalecenia — nierozstrzygnięte”) i pokazuje porównanie kontekstu obu dokumentów. (Decyzja 2026-11-22)
- Obie wersje można skopiować razem z ich źródłami (numer cytatu i identyfikator dokumentu). (Decyzja 2026-11-22)

Ilustracja: 4 (różne zalecenia źródeł, dokument B syntetyczny).

### US-04: Redaktor przegląda listę analiz

Dodane decyzją 2026-11-22 (FR-010).

- **Given** redaktor w roli redaktora
- **When** otwiera listę analiz i decyzji
- **Then** widzi przygotowane przykłady syntetyczne oraz analizy utworzone w swojej sesji, z oceną systemu i stanem decyzji, i może je filtrować

#### Acceptance Criteria

- Listę można filtrować po ocenie systemu i po decyzji człowieka.
- Lista ma osobny stan pustej listy i osobny stan braku wyników filtrowania.
- Wspólna część listy zawiera wyłącznie przygotowane przykłady syntetyczne; analizy odwiedzającego są widoczne tylko w jego sesji.
- Ocena systemu i decyzja człowieka są pokazane w osobnych kolumnach lub polach.

Ilustracja: 5 (lista analiz i jej stany).

## Functional Requirements

Status listy: w fazie 4 użytkownik nie rozstrzygnął, czy lista jest kompletna i poprawnie spriorytetyzowana („Nie wiem”); lista zweryfikowana rundą Sokratesową (faza 4.5) — zmiany: FR-004 doprecyzowany, dodany FR-017 (nice-to-have). 22.11.2026 doprecyzowano FR-008 i FR-009 oraz dodano FR-018–FR-022 na podstawie makiet. Patrz Open Questions, pozycja 2.

### Pytania i odpowiedzi (RAG)

- FR-001: Konsultant can zadać pytanie w języku naturalnym dotyczące bazy wiedzy. Priority: must-have
  > Socrates: Rozważono pytania spoza domeny korpusu (zawsze kończą się abstencją). Resolution: FR bez zmian; użytkownik zaproponował wyszukiwanie w internecie z groundingiem — dodane jako osobny FR-017 (nice-to-have).
  > Decyzja 2026-11-22: w MVP pytania są po angielsku (patrz FR-018).
- FR-002: Konsultant can otrzymać odpowiedź, w której każda istotna teza ma cytat (dokument, fragment, migawka). Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-003: Konsultant can otrzymać jawny komunikat o braku wystarczających dowodów zamiast odpowiedzi. Priority: must-have
  > Socrates: Kontrargument przyjęty do rozważenia: „nadmierna abstencja — system może odmawiać zbyt często i być bezużyteczny; trzeba mierzyć także fałszywe odmowy”. Resolution: FR zachowany; ryzyko przekazane do ewaluacji abstencji (FR-014).
  > Decyzja 2026-11-22: komunikat zawiera wyjaśnienie i listę sprawdzonych fragmentów (US-01).
- FR-004: Konsultant can otworzyć cytowany fragment z jego sąsiedztwem w dokumencie źródłowym, z możliwością otwarcia całego dokumentu. Priority: must-have
  > Socrates: Kontrargument: „dokumenty do 178 KB, zaszumione (logi, powtórzenia)”. Resolution: FR zmieniony — domyślnie fragment z sąsiedztwem, cały dokument na żądanie.
- FR-005: Konsultant can zobaczyć obie strony, gdy źródła są sprzeczne (z datą/wersją, jeśli znane). Priority: must-have
  > Socrates: Kontrargument przyjęty do rozważenia: „brak naturalnych sprzeczności — jedna migawka TechQA bez historii wersji; sprzeczności trzeba wytworzyć syntetycznie”. Resolution: FR zachowany jako must-have; ryzyko demonstrowalności na prawdziwych danych odnotowane (Open Questions).
  > Decyzja 2026-11-22: nazwa stanu zależy od zakresu dokumentów (US-03).

### Audyt rozwiązanego zgłoszenia

- FR-006: Konsultant can ręcznie przekazać do analizy opis rozwiązanego zgłoszenia i notatkę z rozwiązaniem. Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-007: Konsultant/redaktor can zobaczyć wyodrębnione problem, środowisko, rozwiązanie, ograniczenia i weryfikowalne tezy z odniesieniem do fragmentów zgłoszenia oraz oznaczeniem brakujących informacji. Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-008: Redaktor can zobaczyć ocenę każdej tezy (poparta / sprzeczna / niewystarczające dowody) oraz ocenę całej notatki (pełne pokrycie / częściowe pokrycie / sprzeczność / niewystarczające dowody) z fragmentami zgłoszenia i dokumentów. Priority: must-have
  > Socrates: Kontrargument przyjęty do rozważenia: „mało danych testowych — pilotaż ma 3 sprawy źródłowe; 4 kategorie wymagają więcej oznaczonych przypadków”. Resolution: FR zachowany; potrzeba rozbudowy zestawu oznaczonego odnotowana (Open Questions).
  > Decyzja 2026-11-22: poprzednie brzmienie przypisywało tezie cztery kategorie, co przeczyło Business Logic; przyjęto trzy kategorie dla tezy i cztery dla notatki, zgodnie z Business Logic i makietami.
- FR-009: Redaktor can zapisać decyzję z uzasadnieniem. Priority: must-have
  > Socrates: Kontrargument przyjęty do rozważenia: „decyzja bez skutku — MVP nie zmienia dokumentacji, więc zapis decyzji niczego nie uruchamia”. Resolution: FR zachowany; wartość zapisanej decyzji poza demo odnotowana jako pytanie otwarte.
  > Decyzja 2026-11-22: decyzja dotyczy każdej tezy osobno; startowa lista czterech kategorii decyzji (US-02).
- FR-010: Redaktor can przeglądać listę analiz i zapisanych decyzji. Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
  > Decyzja 2026-11-22: z filtrami i stanami listy (US-04).
- FR-021: Redaktor can zobaczyć historię analizy (utworzenie, ocena systemu, zapis decyzji człowieka). Priority: must-have

### Wspólne dla obu przepływów

- FR-019: Konsultant can skopiować odpowiedź albo obie wersje zaleceń razem z ich cytatami. Priority: must-have
- FR-020: Konsultant/redaktor can zobaczyć szczegóły przygotowania odpowiedzi lub analizy (migawka, zakres wyszukiwania). Priority: must-have

### Role i interfejs

- FR-011: Użytkownik can przełączać rolę konsultant/redaktor w interfejsie. Priority: must-have
  > Socrates: Kontrargument przyjęty do rozważenia: „mylny sygnał bezpieczeństwa — przełącznik może sugerować kontrolę dostępu, której nie ma”. Resolution: FR zachowany; interfejs musi jawnie komunikować, że przełącznik ról nie jest kontrolą dostępu.
- FR-018: Użytkownik can przełączać język interfejsu (polski / angielski); interfejs informuje, że pytania, odpowiedzi i analiza są w MVP po angielsku. Priority: must-have
- FR-022: Użytkownik can włączyć ciemny motyw. Priority: nice-to-have

### Dane i pomiar (aktor: operator — autor projektu)

- FR-012: Operator can zaimportować migawkę TechQA z zapisem rewizji i hashy, idempotentnie. Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-013: Operator can uruchomić porównanie retrieval leksykalne vs hybrydowe (Recall@k) na zamrożonym zestawie. Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-014: Operator can uruchomić ewaluację abstencji i sprzeczności na oznaczonym zestawie. Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-015: Operator can uruchomić ewaluację audytu na oznaczonym zestawie (wyniki per kategoria, macierz pomyłek). Priority: must-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.

### Rozszerzenia (nice-to-have)

- FR-016: Konsultant can ręcznie zgłosić błąd w wiedzy. Priority: nice-to-have
  > Socrates: Bez kontrargumentu; FR stoi jak zapisany.
- FR-017: Konsultant can otrzymać odpowiedź uzupełnioną o publiczne źródła internetowe z groundingiem, jawnie oznaczone jako zewnętrzne (URL, data pobrania, fragment). Priority: nice-to-have
  > Socrates: Kontrargument przyjęty do rozważenia: „internet nie potwierdza firmowych procedur — źródło zewnętrzne może dotyczyć innej wersji produktu; potrzebna polityka autorytetu domen i oznaczanie konfliktów”. Resolution: FR zachowany jako nice-to-have.

## Non-Functional Requirements

- Odtwarzalność: każdy opublikowany wynik ewaluacji da się odtworzyć z zapisanej migawki danych (rewizja źródła, hashe plików) i zapisanej konfiguracji (wersje modeli, promptów, parametrów wyszukiwania); ponowny import tej samej migawki daje identyczny stan bazy.
- Czas odpowiedzi w trybie pytań: odpowiedź lub abstencja widoczna dla konsultanta w p95 < 10 s, z ciągłą widoczną informacją o postępie podczas każdej operacji trwającej dłużej niż 2 s.
- Czas analizy rozwiązanego zgłoszenia: mierzony i raportowany (mediana, p95) bez celu w MVP.
- Status tezy i całej notatki jest zawsze rozpoznawalny bez rozróżniania kolorów (słowo i znak, nie sam kolor); brak dowodu nie jest przedstawiany jako błąd. (Źródło: decyzje w `design/mockups/README.md`)
- Ocena systemu i decyzja człowieka są zawsze widoczne jako dwie odrębne informacje; żadna decyzja nie jest wybrana z góry. (Źródło: decyzje w `design/mockups/README.md`)
- Szerokość okna (Decyzja 2026-11-22): produkt jest używany głównie na komputerze, w oknie o szerokości 1280 px i większej. Przepływ „pytanie → odpowiedź → dowód” oraz przepływ „przegląd audytu → decyzja” dają się wykonać do końca także w oknie o szerokości 390 px, bez utraty funkcji i bez przewijania w poziomie. Przekazanie sprawy, różne zalecenia źródeł i lista analiz są w oknie 390 px czytelne i używalne.
- Język (Decyzja 2026-11-22): cały interfejs jest dostępny po polsku i po angielsku. Cytowane fragmenty są dosłowne i pozostają w języku źródła.

## Business Logic

Każda teza — w odpowiedzi dla konsultanta i w notatce z rozwiązanego zgłoszenia — jest klasyfikowana względem bazy wiedzy jako poparta, sprzeczna lub bez wystarczającego dowodu; system przedstawia tylko tezy poparte cytatem, a pozostałe zgłasza do decyzji człowieka.

Wejścia: pytanie lub opis zgłoszenia konsultanta; w audycie — opis rozwiązanej sprawy i notatka z rozwiązaniem; zaindeksowana migawka bazy wiedzy (dokumenty i fragmenty z identyfikatorami i wersją migawki). Teza jest poparta tylko wtedy, gdy cytowany fragment wspiera **konkretnie tę tezę**, a nie jedynie podobny temat. Sprzeczność dotyczy tego samego zakresu (produkt, wersja, kontekst); dokument dla innej wersji lub okresu nie jest automatycznie sprzeczny. Brak wyniku wyszukiwania oznacza „niewystarczające dowody”, nie dowód luki w całej bazie; treść zgłoszenia nie jest automatycznie prawdą.

Wyjście w trybie pytań: odpowiedź złożona wyłącznie z tez popartych cytatem albo jawna abstencja; przy nierozstrzygalnej sprzeczności — obie strony z cytatami. Wyjście w trybie audytu: ocena każdej tezy osobno, a następnie całej notatki w kategoriach pełne pokrycie (wszystkie tezy poparte) / częściowe pokrycie (co najmniej jedna poparta, inna bez dostatecznego dowodu) / sprzeczność (co najmniej jedna teza sprzeczna z dokumentem o tym samym zakresie) / niewystarczające dowody — z fragmentami zgłoszenia i dokumentów.

Użytkownik napotyka regułę w dwóch miejscach: konsultant widzi cytaty lub komunikat o braku dowodów przy każdej odpowiedzi; redaktor widzi oceny tez i dowody, po czym zapisuje decyzję z uzasadnieniem. System nigdy sam nie zmienia ani nie publikuje dokumentacji.

## Access Control

Brak logowania w MVP. Publiczne demo na publicznych danych (TechQA); rola (konsultant / redaktor) wybierana przełącznikiem w interfejsie. Decyzje redaktora są zapisywane z etykietą wybranej roli. Jawnie: przełącznik ról NIE jest kontrolą dostępu — każdy odwiedzający może przyjąć dowolną rolę, a interfejs musi to jawnie komunikować (FR-011). Egzekwowanie uprawnień (uwierzytelnienie, egzekwowana kontrola dostępu oraz gwarancja, że materiały niedostępne dla danej osoby nie trafiają do odpowiedzi ani do logów) jest wymagane dopiero przy danych niepublicznych lub scenariuszu wieloużytkownikowym — poza MVP.

Widoczność danych w demo (Decyzja 2026-11-22): wspólna lista analiz zawiera wyłącznie przygotowane przykłady syntetyczne. Analizy, historia i decyzje utworzone przez odwiedzającego są dostępne tylko w jego sesji i nie trafiają na wspólną listę. Rozdzielenie sesji bez logowania nie jest systemem kont ani uprawnień i nie może być tak przedstawiane.

| Rola (wybrana przełącznikiem) | Co może zrobić w MVP |
|---|---|
| Konsultant | zadać pytanie, otworzyć dowód, skopiować odpowiedź z cytatami, przekazać rozwiązaną sprawę do analizy (FR-001–FR-007, FR-019, FR-020) |
| Redaktor | przejrzeć oceny tez i dowody, zapisać decyzję z uzasadnieniem dla każdej tezy, przeglądać listę i historię analiz (FR-007–FR-010, FR-020, FR-021) |
| Operator (autor projektu) | import danych i uruchamianie ewaluacji (FR-012–FR-015); nie jest rolą w przełączniku |

Ilustracja na makietach: przełącznik „Konsultant / Redaktor” i oznaczenie DEMO na każdym ekranie; w ekranie 3 informacja „Rola «Redaktor» bez weryfikacji tożsamości”.

## Non-Goals

- Integracja z systemem zgłoszeń — rozwiązane sprawy są przekazywane do analizy ręcznie (FR-006); konektory do narzędzi helpdesk to późniejszy etap.
- Prawdziwa kontrola dostępu — brak kont, uwierzytelnienia i danych niepublicznych; przełącznik ról w demo nie jest zabezpieczeniem, a rozdzielenie sesji nie jest systemem kont. Egzekwowanie uprawnień wymagane dopiero przy danych prywatnych lub wielu użytkownikach.
- Edycja i publikacja dokumentacji — zapis decyzji redaktora nie zmienia ani nie publikuje dokumentacji (Business Logic, US-02).
- Wyszukiwanie w internecie — FR-017 jest nice-to-have i nie wchodzi do MVP; odpowiedzi opierają się wyłącznie na migawce TechQA.
- Ręczne zgłaszanie błędu w wiedzy — FR-016 jest nice-to-have i nie wchodzi do MVP.
- Pytania i odpowiedzi po polsku — w MVP pytania, odpowiedzi i analiza są po angielsku, zgodnie z korpusem i danymi ewaluacyjnymi. Obsługa polskich pytań i odpowiedzi to rozszerzenie wymagające osobnych testów wyszukiwania i zgodności odpowiedzi ze źródłami. (Decyzja 2026-11-22)
- Ciemny motyw — FR-022 jest nice-to-have i nie jest wymagany w MVP; wersje „Dark” na kanwie to kierunek. (Decyzja 2026-11-22)

## Open Questions

Pozycje 1–8 pochodzą z shape-notes. Pozycje 9–12 wynikają z decyzji z 22.11.2026. Rozstrzygnięte 22.11.2026 rozbieżności z makietami są wymienione na końcu.

1. **Progi liczbowe Primary** — próg Recall@k dla wyszukiwania hybrydowego (ustalany po zmierzeniu baseline leksykalnego) oraz próg zgodności kategorii audytu (ustalany na zestawie deweloperskim/pilotażu). Owner: użytkownik. By: przed uruchomieniem końcowego testu niezależnego; progi zamrożone przed testem.
2. **Kompletność i priorytety FR** — w fazie 4 użytkownik odpowiedział „Nie wiem” na pytanie o kompletność listy; lista przeszła rundę Sokratesową, ale nie została jawnie zatwierdzona. FR-018–FR-022 dodano 22.11.2026. Owner: użytkownik.
3. **Demonstrowalność FR-005 (sprzeczności)** — jedna migawka TechQA bez historii wersji; sprzeczności trzeba przygotować syntetycznie i oznaczyć. Owner: użytkownik.
4. **Rozmiar zestawu oznaczonego dla audytu (FR-008/FR-015)** — pilotaż ma 12 przypadków z 3 spraw źródłowych w kontrakcie jednego dokumentu; niezależny test wymaga nowych spraw i ręcznego oznaczania. Ile przypadków i kiedy? Owner: użytkownik.
5. **Wartość zapisanej decyzji redaktora (FR-009)** — w MVP decyzja niczego nie uruchamia (brak zmian w dokumentacji); co ma z nią się dziać poza demo? Owner: użytkownik.
6. **Typ produktu** — web-app + data-pipeline; frontmatter przyjmuje `web-app`. Plansza Main i AGENTS.md mówią o „aplikacji desktopowej”; decyzja 2026-11-22 doprecyzowuje to jako aplikację używaną głównie na komputerze (NFR „Szerokość okna”). Owner: użytkownik.
7. **Zakres eksperymentów Secondary** — cache, chunking, reranking są kryteriami Secondary; agentic RAG / Graph RAG / obsługa wielu migawek / grupowanie spraw nie zostały jawnie wykluczone w Non-Goals, mimo że założenia odkładają je na później. Potwierdzić, że nie wchodzą do 8-tygodniowego MVP. Owner: użytkownik.
8. **Weryfikacja etykiet `is_impossible`** — 300 pytań bez kontekstu nie dowodzi braku odpowiedzi w korpusie; 19 grup identycznych pytań, w tym pary z przeciwnymi flagami (przeciek TRAIN/DEV). Wymaga ręcznego przeglądu przed ewaluacją abstencji. Owner: użytkownik.
9. **Domyślny język interfejsu (FR-018)** — polski czy angielski. Owner: użytkownik. By: podczas projektowania interfejsu.
10. **Czas przechowywania danych sesji** — jak długo analizy, historia i decyzje odwiedzającego są przechowywane przed usunięciem. Owner: użytkownik. By: przed publicznym udostępnieniem demo.
11. **Przepływ danych do usług zewnętrznych** — jakie dane odwiedzającego trafiają do zewnętrznych usług przetwarzających treść, do logów i do śladów zapytań. Owner: plan techniczny (opis wymagany przed publicznym udostępnieniem demo).
12. **Makiety po decyzjach** — kanwa została dostosowana 22.11.2026 (wersja 21): plansza Main, zakres audytu w 3/3N/3N-D, pytania i odpowiedzi po angielsku, przełącznik języka PL/EN, lista w ekranie 5 (przykłady demo i analizy z sesji), ostrzeżenie o danych w ekranie 2. Nagłówek ekranu 4 („różne zalecenia — nierozstrzygnięte”) był już zgodny z decyzją. Wąskie wersje ekranów 2, 4 i 5 nie powstały (decyzja: bez osobnych makiet). Owner: użytkownik (przegląd wizualny kanwy).

Rozstrzygnięte 22.11.2026: kategorie tezy (3 dla tezy, 4 dla notatki), decyzja per teza, startowa lista kategorii decyzji, zakres szukania w audycie (cała migawka), szerokości okna, język, nazwa stanu różnych zaleceń, treść komunikatu o braku dowodów, funkcje z makiet (filtry i stany listy, kopiowanie z cytatami, szczegóły procesu, historia analizy), dane osobowe i widoczność analiz, ciemny motyw.
