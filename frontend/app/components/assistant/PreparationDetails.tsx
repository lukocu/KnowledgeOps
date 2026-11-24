import type { AnswerRecord } from "../../api/answers";
import { useT } from "../../i18n/context";
import { chunkSetVariant, snapshotShort } from "../../lib/snapshot";
import { ChevronIcon } from "./Icon";

function formatDuration(ms: number | null): string | null {
  if (ms === null) return null;
  return `${(ms / 1000).toFixed(1)} s`;
}

/**
 * Szczegóły przygotowania (zwinięte `<details>`): wyłącznie wartości z `AnswerRecord`.
 * Wariant „abstained” podaje rzeczywisty powód braku odpowiedzi.
 */
export function PreparationDetails({ record }: { record: AnswerRecord }) {
  const t = useT();
  const result = record.result;
  if (!result) return null;

  const k = record.config.k;
  const model = record.config.chat_model;
  const duration = formatDuration(record.duration_ms);
  const variant = chunkSetVariant(record.chunk_set_id);
  const scope =
    typeof k === "number"
      ? t("details.scopeValue", { variant, k })
      : t("details.scopeValueNoK", { variant });

  const rows: { label: string; value: React.ReactNode }[] = [
    {
      label: t("details.snapshot"),
      value: (
        <span className="font-mono">{snapshotShort(record.snapshot_id)}</span>
      ),
    },
    { label: t("details.scope"), value: scope },
    {
      label: t("details.checkedChunks"),
      value: String(result.checked_chunks.length),
    },
    { label: t("details.omitted"), value: String(result.omitted_claims) },
  ];

  if (result.outcome === "abstained") {
    const reasons = {
      no_hits: "details.reasonNoHits",
      no_claims: "details.reasonNoClaims",
      none_supported: "details.reasonNoneSupported",
    } as const;
    rows.push({ label: t("details.reason"), value: t(reasons[result.reason]) });
  }

  rows.push(
    {
      label: t("details.model"),
      value:
        typeof model === "string" && model !== ""
          ? model
          : t("details.unknown"),
    },
    { label: t("details.duration"), value: duration ?? t("details.unknown") },
  );

  return (
    <details className="group border-t border-border-soft">
      <summary className="flex min-h-6 cursor-pointer list-none items-center gap-2 px-0.5 py-2.5 text-sm text-text [&::-webkit-details-marker]:hidden">
        <span className="inline-flex text-muted transition-transform group-open:rotate-90">
          <ChevronIcon direction="right" size={16} />
        </span>
        <span className="flex-1">
          {t(
            result.outcome === "answered"
              ? "details.answeredTitle"
              : "details.abstainedTitle",
          )}
        </span>
        <span className="text-xs text-muted">{t("details.hint")}</span>
      </summary>
      <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 pr-0.5 pb-3 pl-[26px] text-[13px] leading-5 text-muted">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <dt>{row.label}</dt>
            <dd className="m-0 text-text">{row.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
