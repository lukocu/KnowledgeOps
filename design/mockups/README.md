# Makiety KnowledgeOps Assistant — plan i stan

Makiety służą do oceny **układu i przepływów**. To nie jest implementacja.

## Źródło makiet

**Jedynym źródłem jest kanwa Claude Design:** https://claude.ai/artifact/8WJyeih7wnWE59CmooYqSH

Kanwa jest prywatna. Ekrany są w niej zapisane jako HTML (nie jako zrzuty). Obok nich leży kopia dokumentów źródłowych w `project/docs/`.

**Lokalna kopia:** `design/mockups/canvas/` zawiera pliki `*.dc.html` (po jednym na ekran) i `canvas.json` (układ kanwy), pobrane z kanwy 22.11.2026 (wersja 21, po dostosowaniu do PRD). To format Claude Design, więc nie otwierają się samodzielnie w przeglądarce (brakuje `support.js` z runtime kanwy). Służą jako wzorzec struktury, markupu i stylów inline do implementacji frontendu. Przy rozbieżności kanwa jest nadrzędna.

Nie korzystamy już z Superdesign. Jego drafty i zrzuty PNG zostały usunięte i nie są punktem odniesienia. Styl jest zdefiniowany przez ekrany na kanwie. To propozycja, nie zatwierdzony design system.

Stan opisu: 22.11.2026. Opis ekranów powstał na podstawie tytułów, układu kanwy i planu ekranów. Nowych ekranów (1P, 2P, 3N-D i wariantów ciemnych) nie weryfikowałem treściowo. Przy zmianie najpierw wczytaj aktualną kanwę.

Wymagania produktu są w `context/foundation/prd.md`. 22.11.2026 ekrany zostały dostosowane do decyzji z PRD: pytania i odpowiedzi po angielsku, przełącznik języka interfejsu PL/EN, audyt sprawdza całą migawkę, lista analiz rozdziela przykłady demo od analiz z sesji, nowe ostrzeżenie o danych w ekranie 2.

## Ekrany na kanwie

| Ekran | Tytuł na kanwie | Uwagi |
|---|---|---|
| Main | Opis projektu i zakres | scenariusze MVP, ograniczenia, dane, decyzje do oceny |
| 1A | Asystent – odpowiedź z panelem dowodu | **wybrany wariant cytatu** (panel boczny) |
| 1P | Asystent – przygotowywanie odpowiedzi | stan postępu |
| 1B | Asystent – karta cytatu (alternatywa) | odrzucona alternatywa dla 1A |
| 1C | Asystent – brak wystarczających dowodów | abstencja w układzie odpowiedzi, bez czerwieni |
| 1N | Asystent – wąskie okno (390 px) | dowód w arkuszu od dołu |
| 2 | Przekaż sprawę do audytu | ręczne pola, bez integracji z systemem zgłoszeń |
| 2P | Przekaż sprawę – analiza trwa | stan postępu |
| 3 | Audyt i decyzja redaktora | przypadek P04 (dane syntetyczne), wariant z panelem decyzji |
| 3N | Audyt – wąskie okno | lista → teza → porównanie → decyzja |
| 3N-D | Audyt – decyzja w arkuszu (wąskie okno) | decyzja w arkuszu |
| 4 | Sprzeczne źródła | dane częściowo syntetyczne |
| 5 | Analizy i decyzje | lista analiz (FR-010): wspólne przykłady syntetyczne i analizy z sesji odwiedzającego |
| Materiały | Materiały źródłowe (pliki .md) | linki do dokumentów w `project/docs/` |
| 1A, 1C, 3, 4, 5 (ciemny) | wersje „Dark” | ciemny motyw |
| 1N, 3N (ciemny) | wersje „Dark” w wąskim oknie | ciemny motyw |

## Podjęte decyzje

1. **Dowód w panelu bocznym (1A)**, nie w małej karcie (1B). Na wąskim ekranie panel jest arkuszem od dołu.
2. **Cytaty jako krótkie numery** (`1 2 3`). Pełna nazwa jest w liście źródeł i w panelu dowodu.
3. **Status to zawsze słowo i ikona**, nie sam kolor.
   - Teza: ● Poparta, ✕ Sprzeczność, ○ Niewystarczające dowody.
   - Cała notatka: ● Pełne pokrycie, ◐ Częściowe pokrycie, ✕ Sprzeczność, ○ Niewystarczające dowody.
   - Brak dowodu jest szary, nie czerwony, bo brak fragmentu nie dowodzi błędu.
4. **Ocena systemu jest oddzielona od decyzji redaktora.** Decyzja dotyczy każdej tezy osobno i nie jest wstępnie wybrana.
5. **Ekran audytu:** dowód i panel decyzji są obok siebie przy 1280 i 1440 px. Szczegóły procesu są zwinięte, ale obecne.
6. **Zapis decyzji nie zmienia dokumentacji.**
7. **Teza ma trzy oceny, cała notatka cztery.** Decyzja redaktora dotyczy każdej tezy, także popartej. Cztery kategorie decyzji z ekranu 3 to lista startowa.
8. **Audyt szuka dowodów w całej migawce bazy** i zawsze pokazuje sprawdzony zakres.
9. **Język:** interfejs po polsku i angielsku z przełącznikiem PL/EN. W MVP pytania, odpowiedzi i analiza są po angielsku, cytaty dosłownie w języku źródła.
10. **Różne zalecenia źródeł:** „sprzeczność” tylko przy tym samym zakresie dokumentów; inaczej neutralne „różne zalecenia — nierozstrzygnięte” (ekran 4).
11. **Publiczne demo:** wspólna lista zawiera tylko przykłady syntetyczne, analizy i decyzje odwiedzającego są widoczne tylko w jego sesji i usuwane po ograniczonym czasie.
12. **Szerokość okna:** głównie komputer (od 1280 px); odpowiedź z dowodem i audyt z decyzją działają w oknie 390 px, ekrany 2, 4 i 5 są tam czytelne i używalne (bez osobnych makiet).

Ograniczenia MVP, które makiety muszą respektować: brak logowania (przełącznik ról nie jest kontrolą dostępu), brak integracji z systemem zgłoszeń, brak edycji i publikacji dokumentacji, brak wyszukiwania w internecie.

## Co jest tylko makietą

- Wszystkie dane i czasy (np. liczba kandydatów, sekundy) są ilustracyjne. To nie są pomiary.
- Stany postępu (1P, 2P) pokazują stan, który w produkcie jest kolejnym stanem tego samego miejsca.
- W 1C pytanie jest symulowane, a lista sprawdzonych fragmentów i uzasadnienia są przykładowe. Tytuły dokumentów są prawdziwe (TechQA).
- W audycie P04 oceny tez, brakujące informacje, czasy i historia są przykładem z pilotażu, nie wynikiem systemu. Kategorie decyzji redaktora są propozycją, bo FR-009 nie określa ich listy.
- W ekranie 4 dokument B (`SYN-KB-0007`, data 2019-03) jest syntetyczny, dodany tylko po to, żeby pokazać sprzeczność. Dokument A (`swg21648497`) i jego fragment są prawdziwe. TechQA ma jedną migawkę bez historii wersji.
- W ekranie 5 oceny to oczekiwane etykiety z pilotażu, nie wyniki systemu.
- Pytania i odpowiedzi (po angielsku) są przykładami, nie wynikami systemu. Polskie teksty interfejsu są bazą tłumaczeń.
- Podział listy w ekranie 5 na „przykłady” i „Twoje (ta sesja)” jest przykładowy.
- Obsługa karty klawiaturą i dotykiem jest wymogiem projektowym, nie została zaobserwowana w źródłach.

## Decyzje otwarte

1. Położenie znacznika przy tezie z blokiem kodu: przed blokiem czy po nim.
2. Krój Inter: sprawdzić licencję i polskie znaki.
3. Teza w audycie: pokazywać dosłowne zdanie z notatki czy tezę przeredagowaną przez system.
4. Zachowanie paneli poniżej 1400 px: zwężony panel czy zwijanie do wąskiej szyny.
5. Zakładki tez w ekranie 3 zakładają niewielką liczbę tez. Dla kilkunastu trzeba przewijania lub listy.
6. Domyślny język interfejsu: polski czy angielski.

Rozstrzygnięte 22.11.2026 (patrz PRD): kategorie decyzji redaktora (lista startowa), nazwa stanu sprzecznych źródeł, ciemny motyw (nice-to-have, FR-022).
