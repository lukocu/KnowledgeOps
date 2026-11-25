import { useEffect, useRef } from "react";

import type { CheckedChunk } from "../../api/answers";
import { useLanguage, useT } from "../../i18n/context";
import { pluralForm } from "../../lib/plural";
import { CloseIcon } from "./Icon";

/** Pierwsze 3 pozycje, reszta po „Pokaż pozostałe”. */
export const CHECKED_PREVIEW = 3;

/** Sekcja fragmentu: ostatni niepusty nagłówek. */
function section(chunk: CheckedChunk): string | null {
  const heading = chunk.headings[chunk.headings.length - 1];
  return heading && heading.trim() !== "" ? heading : null;
}

/** Panel sprawdzonych fragmentów (1C): lista `checked_chunks` z „Otwórz fragment”. */
export function CheckedChunksPanel({
  chunks,
  showAll,
  onShowAll,
  onOpen,
  onClose,
}: {
  chunks: CheckedChunk[];
  showAll: boolean;
  onShowAll: () => void;
  onOpen: (index: number, trigger: HTMLElement) => void;
  onClose: () => void;
}) {
  const t = useT();
  const { lang } = useLanguage();
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  const visible = showAll ? chunks : chunks.slice(0, CHECKED_PREVIEW);
  const hidden = chunks.length - visible.length;

  return (
    <aside
      aria-label={t("checked.panel")}
      className="flex w-[min(420px,45%)] min-w-[300px] flex-none flex-col overflow-y-auto border-l border-border-soft bg-surface-alt px-6 pt-3 pb-4"
    >
      <div className="flex items-center justify-between">
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="m-0 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase"
        >
          {t("checked.title", { shown: visible.length, total: chunks.length })}
        </h2>
        <button
          type="button"
          aria-label={t("checked.close")}
          title={t("checked.close")}
          onClick={onClose}
          className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted hover:bg-surface"
        >
          <CloseIcon />
        </button>
      </div>
      <p className="mt-1.5 mb-1 text-[13px] leading-5 text-muted">
        {chunks.length > 0 ? t("checked.intro") : t("checked.empty")}
      </p>
      <ul className="m-0 list-none p-0">
        {visible.map((chunk, index) => {
          const sectionName = section(chunk);
          return (
            <li
              key={chunk.chunk_id}
              className="border-b border-border-soft py-3"
            >
              <div className="text-xs leading-[18px] text-muted">
                <span className="font-mono">{chunk.doc_id}</span>
                {sectionName ? ` · ${sectionName}` : null}
              </div>
              <div className="mt-0.5 line-clamp-2 text-sm leading-5 font-semibold">
                {chunk.title}
              </div>
              <div className="mt-0.5">
                <button
                  type="button"
                  data-chunk-index={index}
                  aria-label={`${t("checked.open")}: ${chunk.doc_id}`}
                  onClick={(event) => onOpen(index, event.currentTarget)}
                  className="inline-flex h-7 cursor-pointer items-center border-0 bg-transparent px-1 text-[13px] font-medium whitespace-nowrap text-primary hover:underline"
                >
                  {t("checked.open")}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {hidden > 0 ? (
        <div className="mt-3.5">
          <button
            type="button"
            onClick={onShowAll}
            className="inline-flex h-9 w-full cursor-pointer items-center justify-center rounded-lg border-0 bg-white px-3 text-[13px] font-medium text-text hover:brightness-95"
          >
            {t(`checked.showMore${pluralForm(lang, hidden)}`, { n: hidden })}
          </button>
        </div>
      ) : null}
    </aside>
  );
}
