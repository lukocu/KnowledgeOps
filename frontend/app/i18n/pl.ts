/** Słownik bazowy (PL, z makiet). Klucze są źródłem prawdy dla `en.ts`. */
export const pl = {
  "app.name": "KnowledgeOps",

  "header.roleGroup": "Rola w interfejsie",
  "header.roleConsultant": "Konsultant",
  "header.roleEditor": "Redaktor",
  "header.roleNotice":
    "Przełącznik ról nie jest zabezpieczeniem ani kontrolą dostępu. Rola nie zmienia uprawnień ani danych.",
  "header.roleNoticeShort": "Rola nie jest kontrolą dostępu",
  "header.demo": "DEMO",
  "header.demoNotice":
    "Publiczne demo portfolio: dane, sprawy i oceny są przykładowe. Przełącznik ról nie jest zabezpieczeniem ani kontrolą dostępu.",
  "header.langGroup": "Język interfejsu",
  "header.langNotice":
    "Język interfejsu. Pytania i odpowiedzi w MVP są po angielsku.",
  "header.langPl": "PL",
  "header.langEn": "EN",
  "header.corpus": "Korpus TechQA",
  "header.corpusSnapshot": "Migawka {revision}",

  "nav.label": "Główna nawigacja",
  "nav.labelRail": "Główna nawigacja (podpisy po najechaniu)",
  "nav.assistant": "Asystent",
  "nav.expand": "Rozwiń menu z podpisami",
  "nav.collapse": "Zwiń menu do ikon",
  "nav.dataSource":
    "Dane: publiczny, historyczny zbiór NVIDIA TechQA-RAG-Eval.",

  "assistant.title": "Asystent",
  "assistant.intro":
    "Zadaj pytanie o produkt, a system odpowie z cytatami albo wskaże brak wystarczających dowodów.",

  "composer.label": "Pytanie do asystenta",
  "composer.placeholder": "Opisz problem lub zadaj pytanie o produkt",
  "composer.placeholderRefine": "Doprecyzuj pytanie",
  "composer.scope":
    "Zakres: cała dokumentacja TechQA · bez internetu · pytania i odpowiedzi po angielsku (MVP)",
  "composer.submit": "Zapytaj",

  "progress.title": "Przygotowuję odpowiedź",
  "progress.search": "Szukanie w dokumentacji",
  "progress.check": "Sprawdzanie, czy fragmenty wspierają odpowiedź",
  "progress.compose": "Składanie odpowiedzi z cytatami",
  "progress.pending": "oczekuje",
  "progress.active": "w toku",
  "progress.done": "zakończone",
  "progress.hint":
    "Jeśli żaden fragment nie wesprze odpowiedzi, zobaczysz komunikat o braku wystarczających dowodów.",

  "answer.loading": "Wczytuję odpowiedź…",
  "answer.heading": "Odpowiedź",
  "answer.scope": "Oparta wyłącznie na fragmentach dokumentacji",
  "answer.scopeDocsOne": "{n} dokument",
  "answer.scopeDocsFew": "{n} dokumenty",
  "answer.scopeDocsMany": "{n} dokumentów",
  "answer.scopeChunksOne": "{n} fragment",
  "answer.scopeChunksFew": "{n} fragmenty",
  "answer.scopeChunksMany": "{n} fragmentów",
  "answer.source": "Źródło · {doc}",
  "answer.sourceFallback": "Fragment {n}",
  "answer.checkedLabel": "Sprawdzone cytaty:",
  "answer.checkedCount": "{x} z {n}",
  "answer.openAll": "Otwórz wszystkie cytaty",
  "answer.copyCode": "Kopiuj",
  "answer.copied": "Skopiowano",
  "answer.copyFailed": "Nie skopiowano",
  "answer.copyCodeLabel": "Kopiuj kod",
  "answer.copyAnswer": "Kopiuj odpowiedź z cytatami",
  "answer.copySources": "Źródła",
  "answer.copySnapshot": "Migawka",
  "citation.label": "Cytat {n} z {total}",

  "details.answeredTitle": "Jak powstała odpowiedź",
  "details.abstainedTitle": "Jak sprawdzono pytanie",
  "details.hint": "szczegóły procesu",
  "details.snapshot": "Migawka",
  "details.scope": "Zakres wyszukiwania",
  "details.scopeValue": "BM25, zestaw {variant}, top {k}",
  "details.scopeValueNoK": "BM25, zestaw {variant}",
  "details.checkedChunks": "Sprawdzone fragmenty",
  "details.omitted": "Pominięte tezy",
  "details.reason": "Powód braku odpowiedzi",
  "details.reasonNoHits":
    "wyszukiwanie nie znalazło żadnych fragmentów pasujących do pytania",
  "details.reasonNoClaims":
    "fragmenty zostały znalezione, ale nie udało się z nich sformułować tezy odpowiadającej na pytanie",
  "details.reasonNoneSupported":
    "sformułowane tezy nie przeszły sprawdzenia: cytat nie występuje we fragmencie albo fragment nie wspiera tezy",
  "details.model": "Model",
  "details.duration": "Czas",
  "details.unknown": "brak danych",

  "evidence.panel": "Panel dowodu",
  "evidence.source": "Źródło {n} z {total}",
  "evidence.fragment": "Fragment {n} z {total}",
  "evidence.prev": "Poprzedni cytat",
  "evidence.next": "Następny cytat",
  "evidence.prevChunk": "Poprzedni fragment",
  "evidence.nextChunk": "Następny fragment",
  "evidence.close": "Zamknij panel dowodu",
  "evidence.supports": "Wspiera tezę {n}",
  "evidence.unknownDate": "data dokumentu: nieznana",
  "evidence.snapshot": "migawka",
  "evidence.moreBefore": "Więcej kontekstu powyżej",
  "evidence.moreAfter": "Więcej kontekstu poniżej",
  "evidence.showDocument": "Pokaż cały dokument",
  "evidence.showWindow": "Wróć do okna kontekstu",
  "evidence.loading": "Wczytuję fragment…",
  "evidence.documentLoading": "Wczytuję dokument…",
  "evidence.unavailable": "Fragment niedostępny w bieżącej migawce.",
  "evidence.documentUnavailable": "Dokument niedostępny w bieżącej migawce.",
  "evidence.error": "Nie udało się wczytać dowodu. Spróbuj ponownie.",
  "evidence.retry": "Spróbuj ponownie",

  "abstain.title": "Nie znaleziono wystarczających dowodów",
  "abstain.explain":
    "W znalezionych fragmentach nie ma materiału, który wspierałby odpowiedź na to pytanie. Dlatego asystent nie podaje odpowiedzi.",
  "abstain.note":
    "To nie oznacza, że informacji nie ma w całym korpusie, ani że odpowiedź brzmi „nie”. Wyszukiwanie mogło jej nie znaleźć.",
  "abstain.actions": "Co możesz zrobić",
  "abstain.refine":
    "Doprecyzuj pytanie, np. podaj wersję produktu albo system operacyjny",
  "abstain.checked": "Sprawdzone fragmenty ({n})",

  "checked.panel": "Sprawdzone fragmenty",
  "checked.title": "Sprawdzone fragmenty · {shown} z {total}",
  "checked.intro":
    "Wyszukiwanie znalazło te fragmenty. Dotyczą podobnego tematu, ale żaden nie wspiera odpowiedzi na to pytanie.",
  "checked.empty": "Wyszukiwanie nie znalazło żadnych fragmentów.",
  "checked.close": "Zamknij panel",
  "checked.open": "Otwórz fragment",
  "checked.showMoreOne": "Pokaż pozostały {n} fragment",
  "checked.showMoreFew": "Pokaż pozostałe {n} fragmenty",
  "checked.showMoreMany": "Pokaż pozostałe {n} fragmentów",

  "errorState.title": "Nie udało się przygotować odpowiedzi",
  "errorState.modelNotConfigured":
    "Brakuje klucza modelu (OPENAI_API_KEY) w konfiguracji backendu. To informacja dla operatora: ustaw klucz i uruchom backend ponownie.",
  "errorState.modelUnavailable":
    "Model nie odpowiedział poprawnie w wymaganym czasie. Spróbuj ponownie.",
  "errorState.databaseUnavailable":
    "Baza danych jest chwilowo niedostępna. Spróbuj ponownie.",
  "errorState.internal": "Wystąpił nieoczekiwany błąd. Spróbuj ponownie.",
  "errorState.note":
    "To awaria po stronie systemu, a nie wynik wyszukiwania: nie wiadomo, czy dokumentacja zawiera odpowiedź.",
  "errorState.retry": "Spróbuj ponownie",
  "errorState.notFoundTitle": "Nie znaleziono odpowiedzi w tej sesji",
  "errorState.notFoundBody":
    "Odpowiedzi są widoczne tylko w sesji, w której powstały. Ten adres może należeć do innej sesji albo odpowiedź nie istnieje.",
  "errorState.newQuestion": "Zadaj nowe pytanie",

  "error.title": "Ups!",
  "error.titleGeneric": "Błąd",
  "error.notFoundTitle": "404",
  "error.notFound": "Nie znaleziono strony.",
  "error.unexpected": "Wystąpił nieoczekiwany błąd.",
} as const;

export type Dictionary = typeof pl;
export type TranslationKey = keyof Dictionary;
