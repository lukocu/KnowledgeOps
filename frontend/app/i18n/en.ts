import type { TranslationKey } from "./pl";

/** Tłumaczenie EN. Brakujący klucz względem `pl.ts` jest błędem `tsc`. */
export const en: Record<TranslationKey, string> = {
  "app.name": "KnowledgeOps",

  "header.roleGroup": "Interface role",
  "header.roleConsultant": "Consultant",
  "header.roleEditor": "Editor",
  "header.roleNotice":
    "The role switch is not a security measure or access control. The role changes neither permissions nor data.",
  "header.roleNoticeShort": "Role is not access control",
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

  "assistant.title": "Assistant",
  "assistant.intro":
    "Ask a product question and the system answers with citations or says there is not enough evidence.",

  "composer.label": "Question for the assistant",
  "composer.placeholder": "Describe the problem or ask a product question",
  "composer.placeholderRefine": "Refine the question",
  "composer.scope":
    "Scope: all TechQA documentation · no internet · questions and answers in English (MVP)",
  "composer.submit": "Ask",

  "progress.title": "Preparing the answer",
  "progress.search": "Searching the documentation",
  "progress.check": "Checking whether the passages support the answer",
  "progress.compose": "Composing the answer with citations",
  "progress.pending": "waiting",
  "progress.active": "in progress",
  "progress.done": "done",
  "progress.hint":
    "If no passage supports an answer, you will see a message about insufficient evidence.",

  "answer.loading": "Loading the answer…",
  "answer.heading": "Answer",
  "answer.scope": "Based only on documentation passages",
  "answer.scopeDocsOne": "{n} document",
  "answer.scopeDocsFew": "{n} documents",
  "answer.scopeDocsMany": "{n} documents",
  "answer.scopeChunksOne": "{n} passage",
  "answer.scopeChunksFew": "{n} passages",
  "answer.scopeChunksMany": "{n} passages",
  "answer.source": "Source · {doc}",
  "answer.sourceFallback": "Passage {n}",
  "answer.checkedLabel": "Citations checked:",
  "answer.checkedCount": "{x} of {n}",
  "answer.openAll": "Open all citations",
  "answer.copyCode": "Copy",
  "answer.copied": "Copied",
  "answer.copyFailed": "Not copied",
  "answer.copyCodeLabel": "Copy code",
  "answer.copyAnswer": "Copy answer with citations",
  "answer.copySources": "Sources",
  "answer.copySnapshot": "Snapshot",
  "citation.label": "Citation {n} of {total}",

  "details.answeredTitle": "How the answer was produced",
  "details.abstainedTitle": "How the question was checked",
  "details.hint": "process details",
  "details.snapshot": "Snapshot",
  "details.scope": "Search scope",
  "details.scopeValue": "BM25, set {variant}, top {k}",
  "details.scopeValueNoK": "BM25, set {variant}",
  "details.checkedChunks": "Passages checked",
  "details.omitted": "Claims omitted",
  "details.reason": "Why there is no answer",
  "details.reasonNoHits": "the search found no passages matching the question",
  "details.reasonNoClaims":
    "passages were found, but no claim answering the question could be drawn from them",
  "details.reasonNoneSupported":
    "the drafted claims failed verification: the quote is not in the passage or the passage does not support the claim",
  "details.model": "Model",
  "details.duration": "Time",
  "details.unknown": "no data",

  "evidence.panel": "Evidence panel",
  "evidence.source": "Source {n} of {total}",
  "evidence.fragment": "Passage {n} of {total}",
  "evidence.prev": "Previous citation",
  "evidence.next": "Next citation",
  "evidence.prevChunk": "Previous passage",
  "evidence.nextChunk": "Next passage",
  "evidence.close": "Close evidence panel",
  "evidence.supports": "Supports claim {n}",
  "evidence.unknownDate": "document date: unknown",
  "evidence.snapshot": "snapshot",
  "evidence.moreBefore": "More context above",
  "evidence.moreAfter": "More context below",
  "evidence.showDocument": "Show the whole document",
  "evidence.showWindow": "Back to the context window",
  "evidence.loading": "Loading the passage…",
  "evidence.documentLoading": "Loading the document…",
  "evidence.unavailable": "Passage not available in the current snapshot.",
  "evidence.documentUnavailable":
    "Document not available in the current snapshot.",
  "evidence.error": "Could not load the evidence. Try again.",
  "evidence.retry": "Try again",

  "abstain.title": "Not enough evidence found",
  "abstain.explain":
    "The retrieved passages contain nothing that would support an answer to this question. That is why the assistant gives no answer.",
  "abstain.note":
    "This does not mean the information is absent from the whole corpus, nor that the answer is “no”. The search may simply have missed it.",
  "abstain.actions": "What you can do",
  "abstain.refine":
    "Refine the question, e.g. add the product version or operating system",
  "abstain.checked": "Passages checked ({n})",

  "checked.panel": "Checked passages",
  "checked.title": "Checked passages · {shown} of {total}",
  "checked.intro":
    "The search found these passages. They are on a similar topic, but none supports an answer to this question.",
  "checked.empty": "The search found no passages.",
  "checked.close": "Close panel",
  "checked.open": "Open passage",
  "checked.showMoreOne": "Show the remaining {n} passage",
  "checked.showMoreFew": "Show the remaining {n} passages",
  "checked.showMoreMany": "Show the remaining {n} passages",

  "errorState.title": "The answer could not be prepared",
  "errorState.modelNotConfigured":
    "The model key (OPENAI_API_KEY) is missing from the backend configuration. This is a note for the operator: set the key and restart the backend.",
  "errorState.modelUnavailable":
    "The model did not respond correctly in the required time. Try again.",
  "errorState.databaseUnavailable":
    "The database is temporarily unavailable. Try again.",
  "errorState.internal": "An unexpected error occurred. Try again.",
  "errorState.note":
    "This is a system failure, not a search result: it is unknown whether the documentation contains an answer.",
  "errorState.retry": "Try again",
  "errorState.notFoundTitle": "Answer not found in this session",
  "errorState.notFoundBody":
    "Answers are visible only in the session that produced them. This address may belong to another session, or the answer does not exist.",
  "errorState.newQuestion": "Ask a new question",

  "error.title": "Oops!",
  "error.titleGeneric": "Error",
  "error.notFoundTitle": "404",
  "error.notFound": "Page not found.",
  "error.unexpected": "An unexpected error occurred.",
};
