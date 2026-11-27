import type {
  AuditClaimResponse,
  AuditDetailResponse,
  AuditHistoryEventType,
  AuditListFilters,
  AuditListItemResponse,
  AuditListSummaryResponse,
  AuditStage,
  AuditStatus,
  ClaimDecisionResponse,
  ClaimVerdict,
  DecisionCategory,
  DecisionStatus,
  NoteVerdict,
} from "../api/audits";
import type { Lang, Translate } from "../i18n/context";
import type { TranslationKey } from "../i18n/pl";
import { pluralForm } from "./plural";
import type { StepStatus } from "./stages";

export const MAX_AUDIT_TEXT_LENGTH = 4000;
export const MAX_CASE_REF_LENGTH = 120;
export const MAX_JUSTIFICATION_LENGTH = 2000;

/** Stała kolejność 4 kategorii decyzji redaktora z PRD (bez wyboru domyślnego). */
export const DECISION_CATEGORIES = [
  "agree_with_system",
  "request_source_or_verify",
  "consider_doc_update",
  "system_verdict_wrong",
] as const satisfies readonly DecisionCategory[];

export type NoteSegment =
  | { kind: "text"; text: string }
  | {
      kind: "claim";
      claimId: string;
      claimIndex: number;
      verdict: ClaimVerdict;
      text: string;
    };

/** Etykieta skrótowa tezy (`T1`, `T2`, …) dla 0-indeksowanego `claim_index`. */
export function claimTag(claimIndex: number): string {
  return `T${claimIndex + 1}`;
}

/**
 * Dzieli `noteText` na segmenty zwykłego tekstu i zakotwiczonych tez (`T1`, `T2`, …).
 * Tezy bez poprawnych offsetów albo nakładające się na wcześniejszą zakotwiczoną tezę
 * są pomijane w podświetleniu notatki, ale pozostają widoczne na liście tez.
 */
export function buildNoteSegments(
  noteText: string,
  claims: readonly Pick<
    AuditClaimResponse,
    "claim_id" | "claim_index" | "verdict" | "source_start" | "source_end"
  >[],
): NoteSegment[] {
  if (noteText.length === 0) return [];

  const anchored = claims
    .filter(
      (
        claim,
      ): claim is typeof claim & {
        source_start: number;
        source_end: number;
      } => claim.source_start !== null && claim.source_end !== null,
    )
    .map((claim) => ({
      claimId: claim.claim_id,
      claimIndex: claim.claim_index,
      verdict: claim.verdict,
      start: Math.max(0, Math.min(claim.source_start, noteText.length)),
      end: Math.max(0, Math.min(claim.source_end, noteText.length)),
    }))
    .filter((item) => item.end > item.start)
    .sort((a, b) => a.start - b.start || a.claimIndex - b.claimIndex);

  const segments: NoteSegment[] = [];
  let cursor = 0;

  for (const item of anchored) {
    if (item.start < cursor) continue;
    if (item.start > cursor) {
      segments.push({ kind: "text", text: noteText.slice(cursor, item.start) });
    }
    segments.push({
      kind: "claim",
      claimId: item.claimId,
      claimIndex: item.claimIndex,
      verdict: item.verdict,
      text: noteText.slice(item.start, item.end),
    });
    cursor = item.end;
  }

  if (cursor < noteText.length) {
    segments.push({ kind: "text", text: noteText.slice(cursor) });
  }

  return segments;
}

export type AuditProgressStepId = "extract" | "retrieve" | "verdict";
export type AuditProgressStep = { id: AuditProgressStepId; status: StepStatus };

/** Mapuje etap i status zadania audytu w tle na 3 kroki panelu postępu (2P). */
export function deriveAuditSteps(
  stage: AuditStage,
  status: AuditStatus,
): AuditProgressStep[] {
  if (status === "completed" || stage === "completed") {
    return [
      { id: "extract", status: "done" },
      { id: "retrieve", status: "done" },
      { id: "verdict", status: "done" },
    ];
  }
  if (stage === "retrieving") {
    return [
      { id: "extract", status: "done" },
      { id: "retrieve", status: "active" },
      { id: "verdict", status: "pending" },
    ];
  }
  if (stage === "verifying" || stage === "aggregating") {
    return [
      { id: "extract", status: "done" },
      { id: "retrieve", status: "done" },
      { id: "verdict", status: "active" },
    ];
  }
  if (status === "failed" || stage === "failed") {
    return [
      { id: "extract", status: "pending" },
      { id: "retrieve", status: "pending" },
      { id: "verdict", status: "pending" },
    ];
  }
  return [
    { id: "extract", status: "active" },
    { id: "retrieve", status: "pending" },
    { id: "verdict", status: "pending" },
  ];
}

export const CLAIM_VERDICT_LABEL: Record<ClaimVerdict, TranslationKey> = {
  supported: "audit.verdict.claim.supported",
  contradicted: "audit.verdict.claim.contradicted",
  insufficient: "audit.verdict.claim.insufficient",
};

export const NOTE_VERDICT_LABEL: Record<NoteVerdict, TranslationKey> = {
  full: "audit.verdict.note.full",
  partial: "audit.verdict.note.partial",
  contradiction: "audit.verdict.note.contradiction",
  insufficient: "audit.verdict.note.insufficient",
};

export const DECISION_CATEGORY_LABEL: Record<DecisionCategory, TranslationKey> =
  {
    agree_with_system: "audit.decision.category.agree_with_system",
    request_source_or_verify:
      "audit.decision.category.request_source_or_verify",
    consider_doc_update: "audit.decision.category.consider_doc_update",
    system_verdict_wrong: "audit.decision.category.system_verdict_wrong",
  };

export const DECISION_STATUS_LABEL: Record<DecisionStatus, TranslationKey> = {
  pending: "audit.decision.status.pending",
  in_progress: "audit.decision.status.in_progress",
  saved: "audit.decision.status.saved",
  not_applicable: "audit.decision.status.not_applicable",
};

export const HISTORY_EVENT_LABEL: Record<
  AuditHistoryEventType,
  TranslationKey
> = {
  audit_created: "audit.history.event.audit_created",
  evaluation_completed: "audit.history.event.evaluation_completed",
  evaluation_failed: "audit.history.event.evaluation_failed",
  decision_saved: "audit.history.event.decision_saved",
  decision_updated: "audit.history.event.decision_updated",
};

/** Czy wartości w formularzu decyzji są identyczne z już zapisaną decyzją. */
export function isDecisionUnchanged(
  category: DecisionCategory | null,
  justification: string,
  savedDecision:
    | Pick<ClaimDecisionResponse, "decision" | "justification">
    | null
    | undefined,
): boolean {
  if (!savedDecision || category === null) return false;
  return (
    savedDecision.decision === category &&
    savedDecision.justification.trim() === justification.trim()
  );
}

/**
 * Czy formularz decyzji redaktora można wysłać: wymaga wybranej kategorii,
 * niepustego uzasadnienia (po `.trim()`, w limicie), braku trwającego zapisu
 * oraz zmiany względem już zapisanej decyzji.
 */
export function canSubmitDecision(
  category: DecisionCategory | null,
  justification: string,
  savedDecision:
    | Pick<ClaimDecisionResponse, "decision" | "justification">
    | null
    | undefined,
  isSaving: boolean,
): boolean {
  if (isSaving || category === null) return false;
  const trimmed = justification.trim();
  if (trimmed.length === 0 || trimmed.length > MAX_JUSTIFICATION_LENGTH) {
    return false;
  }
  if (isDecisionUnchanged(category, justification, savedDecision)) {
    return false;
  }
  return true;
}

/**
 * Czy zdarzenie klawiatury pochodzi z pola edytowalnego (`INPUT`, `TEXTAREA`,
 * `SELECT` albo `contentEditable`), dla którego nie przechwytujemy skrótów.
 */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || typeof target !== "object") return false;
  const element = target as {
    tagName?: unknown;
    isContentEditable?: unknown;
  };
  if (element.isContentEditable === true) return true;
  if (typeof element.tagName === "string") {
    const tag = element.tagName.toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }
  return false;
}

/** Formatuje znacznik czasu ISO w lokalnym formacie PL/EN. */
export function formatAuditTimestamp(iso: string, lang: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const locale = lang === "en" ? "en-GB" : "pl-PL";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

/** Czy audyt obejmował syntetyczną nakładkę korpusu (`synthetic@v1`). */
export function hasSyntheticScope(
  audit: Pick<AuditDetailResponse, "include_synthetic" | "chunk_set_ids">,
): boolean {
  return (
    audit.include_synthetic ||
    audit.chunk_set_ids.some((id) => id.startsWith("synthetic@"))
  );
}

/** Zlicza unikalne dokumenty sprawdzone łącznie we wszystkich tezach audytu. */
export function countUniqueCheckedDocs(
  claims: readonly Pick<AuditClaimResponse, "checked_docs">[],
): number {
  const seen = new Set<string>();
  for (const claim of claims) {
    for (const doc of claim.checked_docs) {
      seen.add(`${doc.snapshot_id ?? ""}:${doc.document_id}`);
    }
  }
  return seen.size;
}

/**
 * Formatuje krótki podział tez pod pigułką oceny notatki na liście analiz
 * (np. „1 poparta · 1 bez wystarczających dowodów”). Zwraca pusty ciąg dla 0 tez.
 */
export function formatClaimBreakdown(
  item: Pick<
    AuditListItemResponse,
    "claims_supported" | "claims_contradicted" | "claims_insufficient"
  >,
  t: Translate,
  lang: Lang = "pl",
): string {
  const parts: string[] = [];
  if (item.claims_contradicted > 0) {
    parts.push(
      t(
        `analyses.breakdown.contradicted${pluralForm(lang, item.claims_contradicted)}`,
        { n: item.claims_contradicted },
      ),
    );
  }
  if (item.claims_supported > 0) {
    parts.push(
      t(
        `analyses.breakdown.supported${pluralForm(lang, item.claims_supported)}`,
        { n: item.claims_supported },
      ),
    );
  }
  if (item.claims_insufficient > 0) {
    parts.push(
      t(
        `analyses.breakdown.insufficient${pluralForm(lang, item.claims_insufficient)}`,
        { n: item.claims_insufficient },
      ),
    );
  }
  return parts.join(" · ");
}

/** Formatuje znacznik czasu ISO w zwartym formacie tabeli (`22.11 10:22` dla PL, `22/11 10:22` dla EN). */
export function formatCompactTimestamp(iso: string, locale = "pl"): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (value: number) => String(value).padStart(2, "0");
  const day = pad(date.getDate());
  const month = pad(date.getMonth() + 1);
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  if (locale.toLowerCase().startsWith("en")) {
    return `${day}/${month} ${hours}:${minutes}`;
  }
  return `${day}.${month} ${hours}:${minutes}`;
}

/** Czy użytkownik ustawił którykolwiek z filtrów wyszukiwania, decyzji lub oceny systemu. */
export function hasActiveSearchOrStatusFilters(
  filters: AuditListFilters,
): boolean {
  return (
    Boolean(filters.q?.trim()) ||
    Boolean(filters.decision_status) ||
    Boolean(filters.note_verdict)
  );
}

/** Czy na liście analiz aktywny jest jakikolwiek filtr (w tym zawężenie źródła). */
export function hasActiveListFilters(filters: AuditListFilters): boolean {
  return (
    hasActiveSearchOrStatusFilters(filters) ||
    (filters.source !== undefined && filters.source !== "all")
  );
}

/** Łączna liczba analiz wymagających decyzji redaktora (`pending` + `in_progress`). */
export function countAwaitingDecision(
  summary: Pick<
    AuditListSummaryResponse,
    "pending_count" | "in_progress_count"
  >,
): number {
  return summary.pending_count + summary.in_progress_count;
}

/** Formatuje pasek podsumowania liczbowego na liście analiz (przed filtrami). */
export function formatSummaryLine(
  summary: AuditListSummaryResponse,
  t: Translate,
  lang: Lang = "pl",
): string {
  return [
    t(`analyses.summary.demo${pluralForm(lang, summary.demo_count)}`, {
      n: summary.demo_count,
    }),
    t("analyses.summary.session", { n: summary.session_count }),
    t(`analyses.summary.pending${pluralForm(lang, summary.pending_count)}`, {
      n: summary.pending_count,
    }),
    t("analyses.summary.inProgress", { n: summary.in_progress_count }),
    t(`analyses.summary.saved${pluralForm(lang, summary.saved_count)}`, {
      n: summary.saved_count,
    }),
  ].join(" · ");
}
