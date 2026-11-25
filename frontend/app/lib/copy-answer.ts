import type { AnsweredResult } from "../api/answers";
import { snapshotShort } from "./snapshot";

const CODE_INDENT = "    ";

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
