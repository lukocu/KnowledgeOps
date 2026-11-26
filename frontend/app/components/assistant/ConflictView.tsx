import { useCallback, useState } from "react";

import {
  getEvidence,
  type AnswerRecord,
  type ConflictComparisonRow,
  type ConflictSide,
  type ConflictingResult,
} from "../../api/answers";
import { useLanguage, useT } from "../../i18n/context";
import { formatConflictForCopy } from "../../lib/copy-answer";
import { pluralForm } from "../../lib/plural";
import { splitSegments, type Range } from "../../lib/segments";
import { useRemote } from "../../lib/use-remote";
import {
  CheckIcon,
  ChevronIcon,
  ContradictionIcon,
  CopyIcon,
  Icon,
  InfoIcon,
} from "./Icon";
import { PreparationDetails } from "./PreparationDetails";
import { useCopy, type CopyState } from "./useCopy";

const ACTION_BUTTON =
  "inline-flex min-h-9 max-w-full cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-surface px-3 py-1.5 text-left text-[13px] font-medium text-text hover:brightness-95";

function CopyStateIcon({ state }: { state: CopyState }) {
  if (state === "copied") {
    return <CheckIcon size={16} className="flex-none text-success" />;
  }
  if (state === "failed") {
    return (
      <Icon>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5M12 16h.01" />
      </Icon>
    );
  }
  return <CopyIcon />;
}

/** Wyróżnia kluczową wartość z tabeli porównawczej w dosłownym cytacie (gdy występuje dosłownie). */
function HighlightedQuote({
  quote,
  highlightValue,
}: {
  quote: string;
  highlightValue: string | null;
}) {
  const ranges: Range[] = [];
  if (highlightValue && highlightValue.trim().length > 0) {
    const needle = highlightValue.trim();
    const index = quote.indexOf(needle);
    if (index >= 0) {
      ranges.push([index, index + needle.length]);
    }
  }

  if (ranges.length === 0) {
    return <>{quote}</>;
  }

  const segments = splitSegments(quote, ranges);
  return (
    <>
      {segments.map((segment, index) =>
        segment.marked ? (
          <mark
            key={index}
            className="rounded-[3px] bg-mark px-[3px] py-px text-inherit [box-decoration-break:clone]"
          >
            <span className="font-mono text-[13px]">{segment.text}</span>
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

function CardContextBody({ chunkId }: { chunkId: string }) {
  const t = useT();
  const load = useCallback(
    (signal: AbortSignal) => getEvidence(chunkId, 1, 0, signal),
    [chunkId],
  );
  const remote = useRemote(load);

  if (remote.status === "loading") {
    return (
      <span className="font-sans text-xs">{t("conflict.contextLoading")}</span>
    );
  }
  if (remote.status === "error" || remote.status === "not_found") {
    return (
      <span className="font-sans text-xs">{t("conflict.contextError")}</span>
    );
  }
  const before = remote.data.window_text
    .slice(0, remote.data.highlight_start)
    .trim();
  if (!before) {
    return (
      <span className="font-sans text-xs">{t("conflict.contextEmpty")}</span>
    );
  }
  return (
    <>
      {remote.data.has_more_before ? "… " : ""}
      {before}
    </>
  );
}

/** Leniwie dociągany kontekst powyżej cytatu (`GET /api/evidence?before=1&after=0`). */
function CardContextDisclosure({ chunkId }: { chunkId: string }) {
  const t = useT();
  const [opened, setOpened] = useState(false);

  return (
    <details
      className="group mt-2"
      onToggle={(event) => {
        if (event.currentTarget.open) setOpened(true);
      }}
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] font-medium text-primary hover:underline [&::-webkit-details-marker]:hidden">
        <span className="inline-flex transition-transform group-open:rotate-90">
          <ChevronIcon direction="right" size={14} />
        </span>
        {t("conflict.contextAbove")}
      </summary>
      <div className="pt-1 pl-5 font-serif text-sm leading-[22px] [overflow-wrap:anywhere] text-muted">
        {opened ? <CardContextBody chunkId={chunkId} /> : null}
      </div>
    </details>
  );
}

function ConflictSourceCard({
  side,
  highlightValue,
  active,
  onOpenSide,
}: {
  side: ConflictSide;
  highlightValue: string | null;
  active: boolean;
  onOpenSide: (side: "A" | "B", trigger: HTMLElement) => void;
}) {
  const t = useT();

  const metaParts: string[] = [];
  if (side.headings.length > 0) {
    metaParts.push(side.headings.join(" › "));
  }
  const datePart = side.doc_date
    ? `${t("conflict.cardDateLabel")}: ${side.doc_date}${
        side.is_synthetic ? ` (${t("conflict.syntheticMetaTag")})` : ""
      }`
    : `${t("conflict.cardDateLabel")}: ${t("conflict.unknownDate")}`;
  metaParts.push(datePart);
  metaParts.push(
    `${t("conflict.cardVersionLabel")}: ${
      side.product_version ?? t("conflict.notProvided")
    }`,
  );

  return (
    <article
      className={
        "min-w-0 flex-1 overflow-hidden rounded-xl bg-white px-4 pt-3.5 pb-4 sm:px-[18px] " +
        (active
          ? "shadow-[inset_0_0_0_1.5px_var(--color-accent)]"
          : "shadow-[inset_0_0_0_1px_var(--color-border-soft)]")
      }
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          className={
            "inline-flex h-6 w-6 flex-none items-center justify-center rounded-md text-[13px] font-semibold " +
            (active
              ? "bg-source-active text-accent-strong"
              : "bg-surface text-text")
          }
        >
          {side.label}
        </span>
        <span className="min-w-0 font-mono text-[13px] break-all">
          {side.doc_id}
        </span>
        <span className="ml-auto">
          {side.is_synthetic ? (
            <span
              title={t("conflict.syntheticTooltip")}
              className="inline-flex cursor-help items-center gap-1.5 rounded-md bg-chip px-2 py-px text-xs leading-5 font-semibold tracking-[.04em] whitespace-nowrap text-chip-text"
            >
              {t("conflict.syntheticBadge")}
              <InfoIcon size={13} />
            </span>
          ) : (
            <span className="inline-block rounded-md bg-surface px-2 py-px text-xs leading-5 font-medium whitespace-nowrap text-muted">
              {t("conflict.techqaBadge")}
            </span>
          )}
        </span>
      </div>

      <div className="mt-1.5 line-clamp-2 text-[15px] leading-[22px] font-semibold">
        {side.title}
      </div>

      <div className="mt-0.5 text-xs leading-[18px] [overflow-wrap:anywhere] text-muted">
        {metaParts.join(" · ")}
      </div>

      <div className="mt-3 py-0.5 pl-3.5 font-serif text-base leading-[27px] [overflow-wrap:anywhere] shadow-[inset_3px_0_0_var(--color-accent)]">
        <HighlightedQuote quote={side.quote} highlightValue={highlightValue} />
      </div>

      {side.code ? (
        <pre className="mt-2.5 mb-0 rounded-lg bg-surface px-3 py-2 font-mono text-[13px] leading-5 [overflow-wrap:anywhere] whitespace-pre-wrap text-text">
          {side.code}
        </pre>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <CardContextDisclosure chunkId={side.chunk_id} />
        <button
          type="button"
          data-conflict-side={side.label}
          aria-pressed={active}
          onClick={(event) => onOpenSide(side.label, event.currentTarget)}
          className="mt-2 inline-flex h-7 cursor-pointer items-center gap-1.5 border-0 bg-transparent px-1 text-[13px] font-medium whitespace-nowrap text-primary hover:underline"
        >
          <Icon size={14}>
            <path d="M14 4h6v6" />
            <path d="M20 4l-9 9" />
            <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
          </Icon>
          {t("conflict.openInPanel")}
        </button>
      </div>
    </article>
  );
}

/**
 * Ekran 4 (S4 / S5): sprzeczne lub różne zalecenia źródeł z tabelą porównawczą,
 * kartami A i B, oznaczeniem dokumentu syntetycznego oraz kopiowaniem obu wersji (FR-019).
 */
export function ConflictView({
  record,
  result,
  activeSide,
  onOpenSide,
  onOpenBoth,
  onRefine,
}: {
  record: AnswerRecord;
  result: ConflictingResult;
  activeSide: "A" | "B" | null;
  onOpenSide: (side: "A" | "B", trigger: HTMLElement) => void;
  onOpenBoth: (trigger: HTMLElement) => void;
  onRefine: () => void;
}) {
  const t = useT();
  const { lang } = useLanguage();
  const { state: copyState, copy } = useCopy();

  const [sideA, sideB] = result.sides;
  const isContradiction = result.conflict_type === "contradiction";
  const titleText = t(
    isContradiction ? "conflict.titleContradiction" : "conflict.titleDifferent",
  );
  const statusText = t(
    isContradiction
      ? "conflict.statusContradiction"
      : "conflict.statusUnresolved",
  );

  const recommendationRow = result.comparison_rows.find(
    (row) => row.kind === "recommendation",
  );

  function rowLabel(row: ConflictComparisonRow): string {
    switch (row.kind) {
      case "recommendation":
        return row.label
          ? t("conflict.rowRecommendationNamed", { label: row.label })
          : t("conflict.rowRecommendation");
      case "audience":
        return t("conflict.rowAudience");
      case "doc_date":
        return t("conflict.rowDate");
      case "product_version":
        return t("conflict.rowVersion");
    }
  }

  function renderCell(
    row: ConflictComparisonRow,
    value: string | null,
    isSynthetic: boolean,
  ) {
    if (!value) {
      return (
        <em className="text-muted">
          {row.kind === "doc_date"
            ? t("conflict.unknownDate")
            : t("conflict.notProvided")}
        </em>
      );
    }
    if (row.kind === "recommendation") {
      const compact = value.length <= 24;
      return (
        <span
          className={
            compact
              ? "font-mono text-lg leading-snug font-semibold [overflow-wrap:anywhere] sm:text-[22px]"
              : "text-sm font-semibold [overflow-wrap:anywhere]"
          }
        >
          {value}
        </span>
      );
    }
    if (row.kind === "doc_date" && isSynthetic) {
      return (
        <span className="[overflow-wrap:anywhere]">
          {value} ({t("conflict.syntheticDateTag")})
        </span>
      );
    }
    return <span className="[overflow-wrap:anywhere]">{value}</span>;
  }

  const refineLabel = result.refine_hint
    ? t("conflict.refineWithHint", { hint: result.refine_hint })
    : t("conflict.refine");

  const extraDocsMessage =
    result.extra_conflicting_docs > 0
      ? t(
          `conflict.extraDocs${pluralForm(lang, result.extra_conflicting_docs)}`,
          { n: result.extra_conflicting_docs },
        )
      : null;

  return (
    <div className="mt-[18px]">
      <div className="flex flex-wrap items-center gap-2.5 sm:gap-3">
        <span
          aria-hidden="true"
          className="inline-flex h-[30px] flex-none items-center justify-center rounded-lg bg-surface px-2 text-[13px] font-semibold text-muted"
        >
          A vs B
        </span>
        <h1 className="m-0 text-[20px] leading-[28px] font-semibold sm:text-[22px] sm:leading-[30px]">
          {titleText}
        </h1>
        {isContradiction ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-conflict-bg py-0.5 pr-3 pl-2.5 text-[13px] leading-[22px] font-semibold whitespace-nowrap text-conflict-text">
            <ContradictionIcon
              size={15}
              className="flex-none text-conflict-icon"
            />
            {statusText}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-md bg-surface px-2 py-0.5 text-xs leading-5 font-medium whitespace-nowrap text-muted">
            <InfoIcon size={14} className="flex-none text-muted" />
            {statusText}
          </span>
        )}
      </div>

      <p className="mt-2 mb-0 max-w-[820px] text-[15px] leading-6 [overflow-wrap:anywhere]">
        {result.summary}
      </p>

      {result.comparison_rows.length > 0 ? (
        <table className="mt-3.5 w-full max-w-[820px] border-collapse">
          <thead>
            <tr>
              <th className="w-[34%] sm:w-auto" />
              <th
                scope="col"
                className="w-[33%] pr-3 pb-1.5 text-left text-xs font-semibold tracking-[.05em] [overflow-wrap:anywhere] text-muted uppercase sm:w-auto sm:pr-4"
              >
                {sideA.label} · {sideA.doc_id}
              </th>
              <th
                scope="col"
                className="w-[33%] pb-1.5 text-left text-xs font-semibold tracking-[.05em] [overflow-wrap:anywhere] text-muted uppercase sm:w-auto"
              >
                {sideB.label} · {sideB.doc_id}
              </th>
            </tr>
          </thead>
          <tbody>
            {result.comparison_rows.map((row, index) => (
              <tr key={`${row.kind}-${index}`}>
                <th
                  scope="row"
                  className="py-1.5 pr-3 text-left align-top text-[13px] font-medium [overflow-wrap:anywhere] text-muted sm:pr-4 sm:whitespace-nowrap"
                >
                  {rowLabel(row)}
                </th>
                <td className="py-1.5 pr-3 align-top text-sm sm:pr-4">
                  {renderCell(row, row.side_a, sideA.is_synthetic)}
                </td>
                <td className="py-1.5 align-top text-sm">
                  {renderCell(row, row.side_b, sideB.is_synthetic)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      <div className="mt-3.5 flex flex-wrap items-center gap-2.5">
        <div className="mr-1.5 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
          {t("conflict.actions")}
        </div>
        <button type="button" onClick={onRefine} className={ACTION_BUTTON}>
          <Icon>
            <path d="M4 20h4L19 9l-4-4L4 16z" />
          </Icon>
          <span className="[overflow-wrap:anywhere]">{refineLabel}</span>
        </button>
        <button
          type="button"
          onClick={(event) => onOpenBoth(event.currentTarget)}
          className={ACTION_BUTTON}
        >
          <Icon>
            <path d="M14 4h6v6" />
            <path d="M20 4l-9 9" />
            <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
          </Icon>
          <span>{t("conflict.openBoth")}</span>
        </button>
        <button
          type="button"
          onClick={() =>
            void copy(
              formatConflictForCopy(result, record.snapshot_id, {
                status: `${titleText} (${statusText})`,
                sources: t("answer.copySources"),
                snapshot: t("answer.copySnapshot"),
                synthetic: t("conflict.syntheticBadge").toLowerCase(),
                date: t("conflict.cardDateLabel"),
                unknownDate: t("conflict.unknownDate"),
                version: t("conflict.cardVersionLabel"),
                notProvided: t("conflict.notProvided"),
              }),
            )
          }
          className={ACTION_BUTTON}
        >
          <CopyStateIcon state={copyState} />
          <span>
            {copyState === "copied"
              ? t("answer.copied")
              : copyState === "failed"
                ? t("answer.copyFailed")
                : t("conflict.copyBoth")}
          </span>
        </button>
        <span role="status" className="sr-only">
          {copyState === "copied"
            ? t("answer.copied")
            : copyState === "failed"
              ? t("answer.copyFailed")
              : ""}
        </span>
      </div>

      {extraDocsMessage ? (
        <div
          role="status"
          className="mt-3.5 flex items-start gap-2 rounded-lg bg-surface px-3.5 py-2.5 text-[13px] leading-5 text-secondary"
        >
          <span className="mt-0.5 flex-none text-muted">
            <InfoIcon size={15} />
          </span>
          <span>{extraDocsMessage}</span>
        </div>
      ) : null}

      <div
        className={
          "mt-[18px] flex flex-col items-stretch gap-4 " +
          (activeSide !== null ? "xl:flex-row" : "lg:flex-row")
        }
      >
        <ConflictSourceCard
          side={sideA}
          highlightValue={recommendationRow?.side_a ?? null}
          active={activeSide === sideA.label}
          onOpenSide={onOpenSide}
        />
        <ConflictSourceCard
          side={sideB}
          highlightValue={recommendationRow?.side_b ?? null}
          active={activeSide === sideB.label}
          onOpenSide={onOpenSide}
        />
      </div>

      <div className="mt-4">
        <PreparationDetails record={record} />
      </div>
    </div>
  );
}
