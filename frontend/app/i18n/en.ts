import type { TranslationKey } from "./pl";

/** Tłumaczenie EN. Brakujący klucz względem `pl.ts` jest błędem `tsc`. */
export const en: Record<TranslationKey, string> = {
  "app.name": "KnowledgeOps",

  "header.roleGroup": "Interface role",
  "header.roleConsultant": "Consultant",
  "header.roleEditor": "Editor",
  "header.roleNotice":
    "The role switch is not a security measure or access control. The role changes neither permissions nor data.",
  "header.demo": "DEMO",
  "header.demoNotice":
    "Public portfolio demo: data, cases and ratings are examples. The role switch is not a security measure or access control.",
  "header.langGroup": "Interface language",
  "header.langNotice":
    "Interface language. Questions and answers are in English in the MVP.",
  "header.langPl": "PL",
  "header.langEn": "EN",
  "header.corpus": "TechQA corpus",
  "header.corpusSnapshot": "Snapshot {revision}",

  "nav.label": "Main navigation",
  "nav.labelRail": "Main navigation (labels on hover)",
  "nav.assistant": "Assistant",
  "nav.expand": "Expand menu with labels",
  "nav.collapse": "Collapse menu to icons",
  "nav.dataSource": "Data: public, historical NVIDIA TechQA-RAG-Eval dataset.",

  "assistant.placeholderTitle": "Assistant",
  "assistant.placeholderBody":
    "Ask a product question and the system answers with citations or says there is not enough evidence. This screen arrives in the next step.",

  "error.title": "Oops!",
  "error.titleGeneric": "Error",
  "error.notFoundTitle": "404",
  "error.notFound": "Page not found.",
  "error.unexpected": "An unexpected error occurred.",
};
