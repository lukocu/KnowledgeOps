import type {
  AuditClaimResponse,
  AuditDetailResponse,
  AuditStage,
  AuditStatus,
  ClaimVerdict,
  NoteVerdict,
} from "../api/audits";
import type { TranslationKey } from "../i18n/pl";
import type { StepStatus } from "./stages";

export const MAX_AUDIT_TEXT_LENGTH = 4000;
export const MAX_CASE_REF_LENGTH = 120;

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
