/** Słownik bazowy (PL, z makiet). Klucze są źródłem prawdy dla `en.ts`. */
export const pl = {
  "app.name": "KnowledgeOps",

  "header.roleGroup": "Rola w interfejsie",
  "header.roleConsultant": "Konsultant",
  "header.roleEditor": "Redaktor",
  "header.roleNotice":
    "Przełącznik ról nie jest zabezpieczeniem ani kontrolą dostępu. Rola nie zmienia uprawnień ani danych.",
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

  "assistant.placeholderTitle": "Asystent",
  "assistant.placeholderBody":
    "Zadaj pytanie o produkt, a system odpowie z cytatami albo wskaże brak wystarczających dowodów. Ten ekran pojawi się w kolejnym kroku.",

  "error.title": "Ups!",
  "error.titleGeneric": "Błąd",
  "error.notFoundTitle": "404",
  "error.notFound": "Nie znaleziono strony.",
  "error.unexpected": "Wystąpił nieoczekiwany błąd.",
} as const;

export type Dictionary = typeof pl;
export type TranslationKey = keyof Dictionary;
