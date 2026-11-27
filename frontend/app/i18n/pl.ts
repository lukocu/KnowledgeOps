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
  "nav.audit": "Przekaż sprawę do audytu",
  "nav.expand": "Rozwiń menu z podpisami",
  "nav.collapse": "Zwiń menu do ikon",
  "nav.menu": "Menu",
  "nav.close": "Zamknij menu",
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
  "details.conflictingTitle": "Jak wykryto rozbieżność",
  "details.hint": "szczegóły procesu",
  "details.snapshot": "Migawka",
  "details.scope": "Zakres wyszukiwania",
  "details.scopeValue": "BM25, zestaw {variant}, top {k}",
  "details.scopeValueNoK": "BM25, zestaw {variant}",
  "details.checkedChunks": "Sprawdzone fragmenty",
  "details.omitted": "Pominięte tezy",
  "details.conflictType": "Klasyfikacja",
  "details.extraConflictingDocs": "Dodatkowe sprzeczne dokumenty",
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
  "evidence.conflictSide": "Źródło {side} ({n} z {total})",
  "evidence.conflictFooter": "Wersja {side}",
  "evidence.prev": "Poprzedni cytat",
  "evidence.next": "Następny cytat",
  "evidence.prevSource": "Poprzednie źródło",
  "evidence.nextSource": "Następne źródło",
  "evidence.prevChunk": "Poprzedni fragment",
  "evidence.nextChunk": "Następny fragment",
  "evidence.close": "Zamknij panel dowodu",
  "evidence.supports": "Wspiera tezę {n}",
  "evidence.docDate": "data dokumentu",
  "evidence.unknownDate": "data dokumentu: nieznana",
  "evidence.productVersion": "wersja produktu",
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

  "conflict.titleDifferent": "Źródła podają różne zalecenia",
  "conflict.titleContradiction": "Sprzeczne zalecenia w dokumentacji",
  "conflict.statusUnresolved": "Nierozstrzygnięte",
  "conflict.statusContradiction": "Sprzeczność",
  "conflict.rowRecommendation": "Zalecana wartość",
  "conflict.rowRecommendationNamed": "Zalecana wartość ({label})",
  "conflict.rowAudience": "Odbiorca dokumentu",
  "conflict.rowDate": "Data dokumentu",
  "conflict.rowVersion": "Wersja produktu",
  "conflict.unknownDate": "nieznana",
  "conflict.notProvided": "nie podano",
  "conflict.syntheticDateTag": "syntetyczna",
  "conflict.syntheticMetaTag": "metadane syntetyczne",
  "conflict.actions": "Co możesz zrobić",
  "conflict.refine": "Doprecyzuj pytanie",
  "conflict.refineWithHint": "Doprecyzuj: {hint}",
  "conflict.openBoth": "Otwórz oba dokumenty",
  "conflict.copyBoth": "Skopiuj obie wersje z cytatami",
  "conflict.techqaBadge": "TechQA",
  "conflict.syntheticBadge": "DOKUMENT SYNTETYCZNY",
  "conflict.syntheticTooltip":
    "Dokument dodany do demo, nie pochodzi z korpusu TechQA.",
  "conflict.cardDateLabel": "data",
  "conflict.cardVersionLabel": "wersja produktu",
  "conflict.contextAbove": "Kontekst powyżej",
  "conflict.contextLoading": "Wczytuję kontekst…",
  "conflict.contextEmpty": "Brak wcześniejszego kontekstu w tym dokumencie.",
  "conflict.contextError": "Nie udało się wczytać kontekstu.",
  "conflict.openInPanel": "Otwórz w panelu dowodu",
  "conflict.extraDocsOne":
    "W sprawdzonych źródłach znaleziono jeszcze {n} dodatkowy dokument podający odmienne zalecenie.",
  "conflict.extraDocsFew":
    "W sprawdzonych źródłach znaleziono jeszcze {n} dodatkowe dokumenty podające odmienne zalecenia.",
  "conflict.extraDocsMany":
    "W sprawdzonych źródłach znaleziono jeszcze {n} dodatkowych dokumentów podających odmienne zalecenia.",

  "abstain.title": "Nie znaleziono wystarczających dowodów",
  "abstain.explain":
    "W znalezionych fragmentach nie ma materiału, który wspierałby odpowiedź na to pytanie. Dlatego asystent nie podaje odpowiedzi.",
  "abstain.note":
    "To nie oznacza, że informacji nie ma w całym korpusie, ani że odpowiedź brzmi „nie”. Wyszukiwanie mogło jej nie znaleźć.",
  "abstain.actions": "Co możesz zrobić",
  "abstain.refine":
    "Doprecyzuj pytanie, np. podaj wersję produktu albo system operacyjny",
  "abstain.checked": "Sprawdzone fragmenty ({n})",
  "abstain.submitAudit": "Przekaż rozwiązaną sprawę do audytu",

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

  "audit.form.title": "Przekaż rozwiązaną sprawę do audytu",
  "audit.form.intro":
    "Wklej opis zgłoszenia i notatkę z rozwiązaniem. System wyodrębni tezy z notatki i porówna każdą z dokumentacją w korpusie. Treść zgłoszenia nie jest traktowana jako prawda.",
  "audit.form.notice":
    "Przekazanie ręczne. Pobieranie spraw z systemu zgłoszeń nie jest częścią MVP. To publiczne demo: nie wklejaj danych osobowych ani poufnych. Analiza będzie widoczna tylko w Twojej sesji i zostanie usunięta po ograniczonym czasie.",
  "audit.form.caseRefLabel": "Identyfikator sprawy",
  "audit.form.caseRefOptional": "(opcjonalny, własny)",
  "audit.form.caseRefPlaceholder": "np. CASE-042",
  "audit.form.descriptionLabel": "Opis problemu lub zgłoszenia",
  "audit.form.required": "(wymagane)",
  "audit.form.descriptionPlaceholder":
    "Opisz produkt, wersję, środowisko i objawy (po angielsku w MVP)",
  "audit.form.descriptionHint":
    "Po angielsku (MVP): produkt, wersja, środowisko i objawy. Brakujące dane system oznaczy w wyniku.",
  "audit.form.noteLabel": "Notatka z rozwiązaniem",
  "audit.form.notePlaceholder":
    "Wklej notatkę z rozwiązaniem zamkniętego zgłoszenia (po angielsku w MVP)",
  "audit.form.noteHint":
    "Po angielsku (MVP), tak jak w zamkniętym zgłoszeniu. Każde twierdzenie będzie sprawdzone osobno.",
  "audit.form.submit": "Uruchom analizę",
  "audit.form.submitting": "Uruchamiam analizę…",
  "audit.form.running": "Analiza trwa…",
  "audit.form.clear": "Wyczyść",
  "audit.form.doesNotChangeDocs": "Analiza nie zmienia dokumentacji.",
  "audit.form.errorRequired":
    "Uzupełnij opis problemu oraz notatkę z rozwiązaniem.",
  "audit.form.errorTooLong": "Przekroczono limit {max} znaków.",
  "audit.form.errorUnavailable":
    "Nie udało się uruchomić analizy (brak konfiguracji modelu albo baza jest niedostępna). Spróbuj ponownie później.",
  "audit.form.errorGeneric":
    "Nie udało się uruchomić analizy. Spróbuj ponownie.",

  "audit.aside.title": "Co się stanie po uruchomieniu",
  "audit.aside.step1Title": "Wyodrębnienie",
  "audit.aside.step1Desc":
    "Problem, środowisko, rozwiązanie, brakujące informacje i tezy z notatki.",
  "audit.aside.step2Title": "Szukanie dowodów",
  "audit.aside.step2Desc":
    "Dla każdej tezy osobno, w dokumentacji korpusu TechQA. Bez internetu.",
  "audit.aside.step3Title": "Ocena tez",
  "audit.aside.step3Desc":
    "Każda teza: poparta, sprzeczna lub z niewystarczającymi dowodami. Potem osobna ocena całej notatki.",
  "audit.aside.step4Title": "Przegląd człowieka",
  "audit.aside.step4Desc":
    "Człowiek przegląda dowody i podejmuje decyzję. System nie zmienia dokumentacji.",

  "audit.progress.title": "Stan analizy",
  "audit.progress.titleWithRef": "Stan analizy {ref}",
  "audit.progress.stepExtract": "Wyodrębnianie kontekstu i tez z notatki",
  "audit.progress.stepExtractDoneOne": "Wyodrębniono {n} tezę",
  "audit.progress.stepExtractDoneFew": "Wyodrębniono {n} tezy",
  "audit.progress.stepExtractDoneMany": "Wyodrębniono {n} tez",
  "audit.progress.stepRetrieve": "Szukanie dowodów dla tez w dokumentacji",
  "audit.progress.stepRetrieveProgress":
    "Szukanie dowodów dla tezy {current} z {total}…",
  "audit.progress.stepRetrieveDone": "Przeszukano dokumentację dla tez",
  "audit.progress.stepVerdict": "Ocena tez i całej notatki",
  "audit.progress.backgroundHint":
    "Analiza działa w tle po stronie serwera. Ten widok odświeża się automatycznie, a adres URL możesz zachować na później w tej sesji.",

  "audit.detail.loading": "Wczytuję analizę…",
  "audit.detail.notFoundTitle": "Nie znaleziono analizy w tej sesji",
  "audit.detail.notFoundBody":
    "Analizy są widoczne tylko w sesji, w której powstały. Ten adres może należeć do innej sesji albo analiza nie istnieje.",
  "audit.detail.failedTitle": "Nie udało się zakończyć analizy",
  "audit.detail.failedBody":
    "Wystąpił błąd podczas analizy notatki. To awaria systemu, a nie ocena dokumentacji.",
  "audit.detail.newAudit": "Przekaż nową sprawę",
  "audit.detail.retryAudit": "Przekaż sprawę ponownie",
  "audit.detail.titleDefault": "Analiza sprawy",
  "audit.detail.titleWithRef": "Analiza {ref}",
  "audit.detail.noteVerdictLabel": "System · ocena całej notatki",
  "audit.detail.noteHeading": "Notatka z rozwiązaniem",
  "audit.detail.claimsHeading": "Tezy z notatki · {n}",
  "audit.detail.noClaims":
    "Nie wyodrębniono żadnych sprawdzalnych tez z tej notatki.",
  "audit.detail.caseContextButton": "Kontekst sprawy",
  "audit.detail.missingInfoOne": "brakuje {n} informacji",
  "audit.detail.missingInfoFew": "brakuje {n} informacji",
  "audit.detail.missingInfoMany": "brakuje {n} informacji",
  "audit.detail.missingInfoNone": "brak brakujących danych",
  "audit.detail.systemRatingHeading": "Ocena systemu",
  "audit.detail.systemRatingSub": "automatyczna, nie jest decyzją",
  "audit.detail.doesNotChangeDocs":
    "Analiza nie zmienia dokumentacji. Człowiek podejmuje decyzję.",
  "audit.detail.insufficientCaveat":
    "Brak znalezionego fragmentu nie dowodzi, że informacja nie istnieje w całej bazie wiedzy ani że notatka jest błędna.",
  "audit.detail.checkedScope": "Sprawdzono:",
  "audit.detail.closestLabel": "(najbliższy)",
  "audit.detail.wholeSnapshot": "cała migawka {snapshot}",
  "audit.detail.syntheticIncluded": "+ dokumenty syntetyczne (synthetic@v1)",
  "audit.detail.evidenceSupportedHeading": "Cytowany fragment",
  "audit.detail.evidenceContradictedHeading": "Sprzeczny fragment",
  "audit.detail.evidenceClosestHeading": "Najbliższy fragment",
  "audit.detail.evidenceDoesNotSupport": "nie wspiera tezy",
  "audit.detail.evidenceSupports": "wspiera tezę",
  "audit.detail.evidenceContradicts": "sprzeczny z tezą",
  "audit.detail.evidenceLabelSupported": "Wspiera tezę {tag}",
  "audit.detail.evidenceLabelContradicted": "Sprzeczny z tezą {tag}",
  "audit.detail.evidenceLabelClosest": "Najbliższy fragment · {tag}",
  "audit.detail.noEvidenceFound":
    "Wyszukiwanie nie znalazło fragmentów pasujących do tej tezy.",
  "audit.detail.showWiderContext": "Pokaż szerszy kontekst",
  "audit.detail.openFullDocument": "Otwórz cały dokument",
  "audit.detail.claimErrorNote":
    "Weryfikacja tej tezy napotkała problem techniczny i została oznaczona jako niewystarczające dowody.",
  "audit.detail.evidencePosition": "Dowód {n} z {total} · {tag}",
  "audit.detail.evidenceFooter": "Teza {tag}",

  "audit.verdict.claim.supported": "Poparta",
  "audit.verdict.claim.contradicted": "Sprzeczność",
  "audit.verdict.claim.insufficient": "Niewystarczające dowody",
  "audit.verdict.note.full": "Pełne pokrycie",
  "audit.verdict.note.partial": "Częściowe pokrycie",
  "audit.verdict.note.contradiction": "Sprzeczność",
  "audit.verdict.note.insufficient": "Niewystarczające dowody",

  "audit.context.panelLabel": "Kontekst sprawy",
  "audit.context.close": "Zamknij kontekst sprawy",
  "audit.context.problem": "Problem",
  "audit.context.environment": "Środowisko",
  "audit.context.solution": "Rozwiązanie",
  "audit.context.constraints": "Ograniczenia i warunki",
  "audit.context.missingInfo": "Brakujące informacje",
  "audit.context.originalDescription": "Oryginalny opis zgłoszenia",
  "audit.context.notProvided": "nie podano w sprawie",
  "audit.context.none": "brak",

  "audit.details.title": "Jak powstała ta analiza",
  "audit.details.claimsCount": "Wyodrębnione tezy",
  "audit.details.checkedDocsCount": "Sprawdzone unikalne dokumenty",
  "audit.details.syntheticScope": "Nakładka syntetyczna",
  "audit.details.syntheticYes": "tak (synthetic@v1)",
  "audit.details.syntheticNo": "nie",

  "audit.decision.panelLabel": "Decyzja redaktora",
  "audit.decision.heading": "Decyzja redaktora dla {tag}",
  "audit.decision.close": "Zamknij panel decyzji",
  "audit.decision.subtitle": "Twoja decyzja, niezależna od oceny systemu.",
  "audit.decision.subtitleSheet":
    "Twoja decyzja, niezależna od oceny systemu (ocena: {verdict}).",
  "audit.decision.radioGroupLabel": "Decyzja",
  "audit.decision.noneSelected": "Nic nie jest wybrane z góry.",
  "audit.decision.justificationLabel": "Uzasadnienie",
  "audit.decision.justificationPlaceholder": "Napisz, dlaczego tak decydujesz",
  "audit.decision.incompleteButton": "Wybierz decyzję i wpisz uzasadnienie",
  "audit.decision.savedButton": "Zapisano",
  "audit.decision.saveButton": "Zapisz decyzję dla {tag}",
  "audit.decision.updateButton": "Zaktualizuj decyzję dla {tag}",
  "audit.decision.saving": "Zapisuję decyzję…",
  "audit.decision.savedConfirmation": "Decyzja została zapisana.",
  "audit.decision.lastSaved": "Zapisano ({role}): {time}",
  "audit.decision.disclaimer":
    "Zapis nie zmienia ani nie publikuje dokumentacji. Rola „Redaktor” bez weryfikacji tożsamości.",
  "audit.decision.consultantReadOnly":
    "Zapis i edycja decyzji są dostępne w roli Redaktor.",
  "audit.decision.switchToEditor": "Przełącz na rolę Redaktor",
  "audit.decision.savedBadge": "Zapisana decyzja",
  "audit.decision.claimSaved": "Zapisana",
  "audit.decision.claimUnsaved": "Bez decyzji",
  "audit.decision.ctaBarTitle": "Decyzja dla {tag}",
  "audit.decision.ctaBarSaved": "zapisano",
  "audit.decision.ctaBarUnsaved": "nie zapisano",
  "audit.decision.errorNotFound":
    "Nie znaleziono analizy lub tezy w bieżącej sesji.",
  "audit.decision.errorNotCompleted":
    "Decyzję można zapisać dopiero po zakończeniu analizy.",
  "audit.decision.errorValidation":
    "Wybierz kategorię decyzji i wpisz uzasadnienie (maks. 2000 znaków).",
  "audit.decision.errorGeneric":
    "Nie udało się zapisać decyzji. Spróbuj ponownie.",

  "audit.decision.category.agree_with_system": "Zgoda z oceną systemu",
  "audit.decision.category.request_source_or_verify":
    "Poproś o źródło lub zweryfikuj",
  "audit.decision.category.consider_doc_update":
    "Rozważ uzupełnienie dokumentacji",
  "audit.decision.category.system_verdict_wrong": "Ocena systemu błędna",

  "audit.decision.status.pending": "Do decyzji",
  "audit.decision.status.in_progress": "Decyzje: {done}/{total}",
  "audit.decision.status.saved": "Zapisana ({done}/{total})",
  "audit.decision.status.not_applicable": "Brak tez do decyzji",

  "audit.history.title": "Historia",
  "audit.history.empty": "Brak zarejestrowanych zdarzeń.",
  "audit.history.countOne": "{n} zdarzenie",
  "audit.history.countFew": "{n} zdarzenia",
  "audit.history.countMany": "{n} zdarzeń",
  "audit.history.last": "ostatnie: {label}",
  "audit.history.actorSystem": "System",
  "audit.history.event.audit_created": "Utworzono analizę",
  "audit.history.event.evaluation_completed": "Zakończono ocenę systemu",
  "audit.history.event.evaluation_failed": "Błąd oceny systemu",
  "audit.history.event.decision_saved": "Zapisano decyzję",
  "audit.history.event.decision_updated": "Zaktualizowano decyzję",
} as const;

export type Dictionary = typeof pl;
export type TranslationKey = keyof Dictionary;
