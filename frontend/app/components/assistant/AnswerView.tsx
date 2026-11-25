import { useEffect, useState } from "react";

import type { AnswerRecord, AnsweredResult } from "../../api/answers";
import { useLanguage, useT } from "../../i18n/context";
import { pluralForm } from "../../lib/plural";
import { CitationMarker } from "./CitationMarker";
import { CheckIcon, CopyIcon, Icon } from "./Icon";
import { PreparationDetails } from "./PreparationDetails";
import { SourcesRow } from "./SourcesRow";

type CopyState = "idle" | "copied" | "failed";

/** Blok kodu pod tezą z przyciskiem „Kopiuj” (kopiuje sam kod). */
function CodeBlock({ code }: { code: string }) {
  const t = useT();
  const [copy, setCopy] = useState<CopyState>("idle");

  useEffect(() => {
    if (copy === "idle") return;
    const timer = window.setTimeout(() => setCopy("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [copy]);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  }

  return (
    <div className="mt-2">
      <div className="rounded-lg bg-surface">
        <div className="flex justify-end px-1.5 pt-1">
          <button
            type="button"
            onClick={() => void copyCode()}
            aria-label={t("answer.copyCodeLabel")}
            className="inline-flex h-7 cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-white px-3 text-xs font-medium whitespace-nowrap text-text hover:brightness-95"
          >
            {copy === "copied" ? (
              <CheckIcon size={16} className="flex-none text-success" />
            ) : copy === "failed" ? (
              <Icon>
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v5M12 16h.01" />
              </Icon>
            ) : (
              <CopyIcon />
            )}
            {copy === "copied"
              ? t("answer.copied")
              : copy === "failed"
                ? t("answer.copyFailed")
                : t("answer.copyCode")}
          </button>
        </div>
        <pre className="m-0 px-3.5 pt-1 pb-2.5 font-mono text-[13px] leading-5 [overflow-wrap:anywhere] whitespace-pre-wrap text-text">
          {code}
        </pre>
      </div>
    </div>
  );
}

/**
 * Odpowiedź z cytatami (1A): tezy z numerami cytatów, wiersz źródeł, status sprawdzonych
 * cytatów i szczegóły przygotowania. Cytaty otwierają panel dowodu (stan w trasie).
 */
export function AnswerView({
  record,
  result,
  activeN,
  opened,
  onOpen,
  onOpenAll,
}: {
  record: AnswerRecord;
  result: AnsweredResult;
  activeN: number | null;
  /** Numery cytatów otwartych w panelu w tym widoku (stan klienta). */
  opened: ReadonlySet<number>;
  onOpen: (n: number, trigger: HTMLElement) => void;
  onOpenAll: (trigger: HTMLElement) => void;
}) {
  const t = useT();
  const { lang } = useLanguage();
  const total = result.citations.length;
  const documents = new Set(result.citations.map((c) => c.doc_id)).size;

  const docsLabel = t(`answer.scopeDocs${pluralForm(lang, documents)}`, {
    n: documents,
  });
  const chunksLabel = t(`answer.scopeChunks${pluralForm(lang, total)}`, {
    n: total,
  });

  return (
    <div>
      <div className="mt-[22px] flex flex-wrap items-baseline gap-2.5">
        <h2 className="m-0 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
          {t("answer.heading")}
        </h2>
        <span className="text-[13px] text-muted">
          {t("answer.scope")} · {docsLabel}, {chunksLabel}
        </span>
      </div>

      <div className="mt-1.5 flex flex-col gap-1.5">
        {result.claims.map((claim, index) => {
          const active = claim.citation === activeN;
          return (
            <div
              key={index}
              className={
                "rounded-sm py-2 pr-3.5 pl-4 text-base leading-[26px] " +
                (active ? "shadow-[inset_3px_0_0_var(--color-accent)]" : "")
              }
            >
              {claim.text}
              <CitationMarker
                n={claim.citation}
                total={total}
                active={active}
                onOpen={(trigger) => onOpen(claim.citation, trigger)}
              />
              {claim.code ? <CodeBlock code={claim.code} /> : null}
            </div>
          );
        })}
      </div>

      <SourcesRow
        citations={result.citations}
        activeN={activeN}
        onOpen={onOpen}
      />

      <div className="mt-[18px] flex flex-wrap items-center gap-4">
        <span
          role="status"
          className="inline-flex items-center gap-2 text-[13px] whitespace-nowrap text-text"
        >
          <span aria-hidden="true" className="inline-flex gap-[3px]">
            {result.citations.map((citation) => (
              <span
                key={citation.n}
                className={
                  "h-1.5 w-[18px] rounded-[3px] " +
                  (opened.has(citation.n) ? "bg-accent" : "bg-border")
                }
              />
            ))}
          </span>
          {t("answer.checkedLabel")}{" "}
          <strong className="font-semibold">
            {t("answer.checkedCount", { x: opened.size, n: total })}
          </strong>
        </span>
        <button
          type="button"
          onClick={(event) => onOpenAll(event.currentTarget)}
          className="inline-flex h-7 cursor-pointer items-center gap-1.5 border-0 bg-transparent px-1 text-[13px] font-medium whitespace-nowrap text-primary hover:underline"
        >
          <Icon size={14}>
            <path d="M14 4h6v6" />
            <path d="M20 4l-9 9" />
            <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
          </Icon>
          {t("answer.openAll")}
        </button>
      </div>

      <div className="mt-3.5">
        <PreparationDetails record={record} />
      </div>
    </div>
  );
}
