import type { AnsweredResult, ConflictingResult } from "../api/answers";
import { snapshotShort } from "./snapshot";

const CODE_INDENT = "    ";

export type ConflictCopyLabels = {
  status: string;
  sources: string;
  snapshot: string;
  synthetic: string;
  date: string;
  unknownDate: string;
  version: string;
  notProvided: string;
};

/**
 * Zwykły tekst odpowiedzi do schowka: tezy z numerami cytatów (kod wcięty pod tezą),
 * lista źródeł `[n] doc_id — tytuł` i skrócona migawka. Pominięte tezy nie trafiają do kopii.
 */
export function formatAnswerForCopy(
  result: AnsweredResult,
  snapshotId: string,
  labels: { sources: string; snapshot: string },
): string {
  const lines: string[] = [];

  for (const claim of result.claims) {
    lines.push(`${claim.text} [${claim.citation}]`);
    if (claim.code) {
      for (const codeLine of claim.code.split("\n")) {
        lines.push(`${CODE_INDENT}${codeLine}`);
      }
    }
  }

  lines.push("", `${labels.sources}:`);
  const seen = new Set<number>();
  const citations = [...result.citations].sort((a, b) => a.n - b.n);
  for (const citation of citations) {
    if (seen.has(citation.n)) continue;
    seen.add(citation.n);
    lines.push(`[${citation.n}] ${citation.doc_id} — ${citation.title}`);
  }
  lines.push(`${labels.snapshot}: ${snapshotShort(snapshotId)}`);

  return `${lines.join("\n")}\n`;
}

/**
 * Zwykły tekst dla sprzecznych źródeł (FR-019): nagłówek stanu, podsumowanie,
 * obie instrukcje (`[A]` i `[B]`) z `doc_id` i opcjonalnymi blokami kodu,
 * sekcja źródeł z metadanymi (syntetyczny/data/wersja) oraz skrócona migawka.
 */
export function formatConflictForCopy(
  result: ConflictingResult,
  recordSnapshotId: string,
  labels: ConflictCopyLabels,
): string {
  const lines: string[] = [labels.status, result.summary, ""];

  for (const side of result.sides) {
    lines.push(`[${side.label}] ${side.claim_text} (${side.doc_id})`);
    if (side.code) {
      for (const codeLine of side.code.split("\n")) {
        lines.push(`${CODE_INDENT}${codeLine}`);
      }
    }
  }

  lines.push("", `${labels.sources}:`);
  for (const side of result.sides) {
    const meta: string[] = [];
    if (side.is_synthetic) meta.push(labels.synthetic);
    meta.push(`${labels.date}: ${side.doc_date ?? labels.unknownDate}`);
    meta.push(
      `${labels.version}: ${side.product_version ?? labels.notProvided}`,
    );
    lines.push(
      `[${side.label}] ${side.doc_id} — ${side.title} (${meta.join(", ")})`,
    );
  }
  lines.push(`${labels.snapshot}: ${snapshotShort(recordSnapshotId)}`);

  return `${lines.join("\n")}\n`;
}
