import type { ReactNode } from "react";

import type { AuditDetailResponse } from "../../api/audits";
import { useT } from "../../i18n/context";
import { countUniqueCheckedDocs, hasSyntheticScope } from "../../lib/audit";
import { chunkSetVariant, snapshotShort } from "../../lib/snapshot";
import { ChevronIcon } from "../assistant/Icon";

function formatDuration(ms: number | null): string | null {
  if (ms === null) return null;
  return `${(ms / 1000).toFixed(1)} s`;
}

/**
 * Zwinięta sekcja „Jak powstała ta analiza” (FR-020): wyłącznie rzeczywiste pola
 * z rekordu audytu, bez wymyślonych metryk.
 */
export function AuditPreparationDetails({
  audit,
}: {
  audit: AuditDetailResponse;
}) {
  const t = useT();
  const k = audit.config.k;
  const model = audit.config.chat_model;
  const duration = formatDuration(audit.duration_ms);
  const primaryChunkSet = audit.chunk_set_ids[0] ?? "";
  const variant = primaryChunkSet
    ? chunkSetVariant(primaryChunkSet)
    : t("details.unknown");
  const scope =
    typeof k === "number"
      ? t("details.scopeValue", { variant, k })
      : t("details.scopeValueNoK", { variant });
  const synthetic = hasSyntheticScope(audit);
  const uniqueDocs = countUniqueCheckedDocs(audit.claims);

  const rows: { label: string; value: ReactNode }[] = [
    {
      label: t("details.snapshot"),
      value: (
        <span className="font-mono">{snapshotShort(audit.snapshot_id)}</span>
      ),
    },
    { label: t("details.scope"), value: scope },
    {
      label: t("audit.details.syntheticScope"),
      value: synthetic
        ? t("audit.details.syntheticYes")
        : t("audit.details.syntheticNo"),
    },
    {
      label: t("audit.details.claimsCount"),
      value: String(audit.claims.length),
    },
    {
      label: t("audit.details.checkedDocsCount"),
      value: String(uniqueDocs),
    },
    {
      label: t("details.model"),
      value:
        typeof model === "string" && model !== ""
          ? model
          : t("details.unknown"),
    },
    { label: t("details.duration"), value: duration ?? t("details.unknown") },
  ];

  return (
    <details className="group border-t border-border-soft">
      <summary className="flex min-h-6 cursor-pointer list-none items-center gap-2 px-0.5 py-2.5 text-sm text-text [&::-webkit-details-marker]:hidden">
        <span className="inline-flex text-muted transition-transform group-open:rotate-90">
          <ChevronIcon direction="right" size={16} />
        </span>
        <span className="flex-1">{t("audit.details.title")}</span>
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
