import { useCallback, useEffect, useRef, useState } from "react";

import { getDocument, getEvidence } from "../../api/answers";
import { useT } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/pl";
import { splitSegments, type Range } from "../../lib/segments";
import { snapshotShort } from "../../lib/snapshot";
import { useRemote } from "../../lib/use-remote";
import { ChevronIcon, CloseIcon, Icon, InfoIcon } from "./Icon";

/** API pozwala na `before`/`after` w zakresie 0–5. */
const MAX_CONTEXT_CHUNKS = 5;
const DEFAULT_CONTEXT_CHUNKS = 1;

export type EvidenceTarget = {
  chunkId: string;
  snapshotId: string;
  docId: string;
  title: string;
  headings: string[];
  /** Cytaty (offsety względem tekstu fragmentu). Puste: zaznaczany jest cały fragment. */
  quotes: { start: number; end: number }[];
  /** Tezy powiązane z tym fragmentem (`index` to numer tezy, od 1). Puste: bez pola. */
  claims: { index: number; text: string; label?: string }[];
  isSynthetic?: boolean;
  docDate?: string | null;
  productVersion?: string | null;
  sideLabel?: "A" | "B";
};

type EvidenceMeta = {
  snapshotId: string;
  isSynthetic: boolean;
  docDate: string | null;
  productVersion: string | null;
};

const LINK_BUTTON_BASE =
  "inline-flex cursor-pointer items-center gap-1.5 border-0 bg-transparent px-1 text-[13px] font-medium whitespace-nowrap text-primary hover:underline disabled:cursor-wait disabled:opacity-60";

const LINK_BUTTON = "h-7 " + LINK_BUTTON_BASE;

/** Przycisk stopki: w wąskim oknie (arkusz 1N) 40 px wysokości. */
const FOOTER_BUTTON = "h-[40px] md:h-7 " + LINK_BUTTON_BASE;

const NAV_BUTTON =
  "inline-flex h-[40px] w-[40px] cursor-pointer items-center justify-center rounded-lg md:h-8 md:w-8 border-0 bg-transparent p-0 text-muted hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

function Notice({
  message,
  action,
}: {
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 text-sm leading-5 text-secondary"
    >
      <span className="text-muted">
        <InfoIcon />
      </span>
      <span>{message}</span>
      {action}
    </div>
  );
}

/**
 * Tekst dowodu: sąsiedztwo wyciszonym krojem szeryfowym, fragment z subtelną granicą,
 * cytaty (albo cały fragment, gdy brak cytatu) w `<mark>` jak na S1A.
 */
function EvidenceText({
  before,
  chunk,
  after,
  quotes,
  hasMoreBefore,
  hasMoreAfter,
  chunkRef,
}: {
  before: string;
  chunk: string;
  after: string;
  quotes: { start: number; end: number }[];
  hasMoreBefore: boolean;
  hasMoreAfter: boolean;
  chunkRef?: React.Ref<HTMLDivElement>;
}) {
  const ranges: Range[] =
    quotes.length > 0
      ? quotes.map((q) => [q.start, q.end] as const)
      : [[0, chunk.length]];
  const segments = splitSegments(chunk, ranges);

  return (
    <div className="flex flex-col gap-3">
      {before ? (
        <div className="font-serif text-[15px] leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap text-muted">
          {hasMoreBefore ? "… " : ""}
          {before}
        </div>
      ) : null}
      <div
        ref={chunkRef}
        className="border-l-2 border-border pl-3 font-serif text-[17px] leading-[29px] [overflow-wrap:anywhere] whitespace-pre-wrap"
      >
        {segments.map((segment, index) =>
          segment.marked ? (
            <mark
              key={index}
              className="rounded-[3px] bg-mark px-[3px] py-px text-inherit [box-decoration-break:clone]"
            >
              {segment.text}
            </mark>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
      </div>
      {after ? (
        <div className="font-serif text-[15px] leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap text-muted">
          {after}
          {hasMoreAfter ? " …" : ""}
        </div>
      ) : null}
    </div>
  );
}

function WindowView({
  target,
  before,
  after,
  attempt,
  onMeta,
  onMoreBefore,
  onMoreAfter,
  onRetry,
}: {
  target: EvidenceTarget;
  before: number;
  after: number;
  attempt: number;
  onMeta: (meta: EvidenceMeta) => void;
  onMoreBefore: () => void;
  onMoreAfter: () => void;
  onRetry: () => void;
}) {
  const t = useT();
  const load = useCallback(
    async (signal: AbortSignal) => {
      void attempt; // nowa próba = nowa tożsamość funkcji = nowe żądanie
      const result = await getEvidence(target.chunkId, before, after, signal);
      if (!signal.aborted) {
        onMeta({
          snapshotId: result.snapshot_id,
          isSynthetic: result.is_synthetic,
          docDate: result.doc_date ?? null,
          productVersion: result.product_version ?? null,
        });
      }
      return result;
    },
    [target.chunkId, before, after, attempt, onMeta],
  );
  const remote = useRemote(load);
  const loading = remote.status === "loading";
  const data =
    remote.status === "ready"
      ? remote.data
      : remote.status === "loading"
        ? remote.previous
        : undefined;

  if (remote.status === "not_found") {
    return <Notice message={t("evidence.unavailable")} />;
  }
  if (remote.status === "error") {
    return (
      <Notice
        message={t("evidence.error")}
        action={
          <button type="button" onClick={onRetry} className={LINK_BUTTON}>
            {t("evidence.retry")}
          </button>
        }
      />
    );
  }
  if (!data) return <Notice message={t("evidence.loading")} />;

  const text = data.window_text;
  const canMoreBefore = data.has_more_before && before < MAX_CONTEXT_CHUNKS;
  const canMoreAfter = data.has_more_after && after < MAX_CONTEXT_CHUNKS;

  return (
    <div aria-busy={loading} className="flex flex-col gap-3">
      {canMoreBefore ? (
        <button
          type="button"
          disabled={loading}
          onClick={onMoreBefore}
          className={LINK_BUTTON + " self-start"}
        >
          <ChevronIcon direction="up" size={14} />
          {t("evidence.moreBefore")}
        </button>
      ) : null}
      <EvidenceText
        before={text.slice(0, data.highlight_start)}
        chunk={text.slice(data.highlight_start, data.highlight_end)}
        after={text.slice(data.highlight_end)}
        quotes={target.quotes}
        hasMoreBefore={data.has_more_before}
        hasMoreAfter={data.has_more_after}
      />
      {canMoreAfter ? (
        <button
          type="button"
          disabled={loading}
          onClick={onMoreAfter}
          className={LINK_BUTTON + " self-start"}
        >
          <ChevronIcon direction="down" size={14} />
          {t("evidence.moreAfter")}
        </button>
      ) : null}
    </div>
  );
}

function DocumentView({
  target,
  attempt,
  onRetry,
}: {
  target: EvidenceTarget;
  attempt: number;
  onRetry: () => void;
}) {
  const t = useT();
  const load = useCallback(
    (signal: AbortSignal) => {
      void attempt;
      return getDocument(target.snapshotId, target.docId, signal);
    },
    [target.snapshotId, target.docId, attempt],
  );
  const remote = useRemote(load);
  const chunkRef = useRef<HTMLDivElement>(null);
  const ready = remote.status === "ready";

  // Po załadowaniu dokumentu przewijamy do cytowanego fragmentu.
  useEffect(() => {
    if (ready) chunkRef.current?.scrollIntoView({ block: "center" });
  }, [ready]);

  if (remote.status === "not_found") {
    return <Notice message={t("evidence.documentUnavailable")} />;
  }
  if (remote.status === "error") {
    return (
      <Notice
        message={t("evidence.error")}
        action={
          <button type="button" onClick={onRetry} className={LINK_BUTTON}>
            {t("evidence.retry")}
          </button>
        }
      />
    );
  }
  if (remote.status === "loading") {
    return <Notice message={t("evidence.documentLoading")} />;
  }

  const doc = remote.data;
  const span = doc.chunks.find((c) => c.chunk_id === target.chunkId);
  if (!span) {
    return (
      <div className="font-serif text-[15px] leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap text-muted">
        {doc.text}
      </div>
    );
  }
  return (
    <EvidenceText
      before={doc.text.slice(0, span.start_offset)}
      chunk={doc.text.slice(span.start_offset, span.end_offset)}
      after={doc.text.slice(span.end_offset)}
      quotes={target.quotes}
      hasMoreBefore={false}
      hasMoreAfter={false}
      chunkRef={chunkRef}
    />
  );
}

/** Ciało panelu; zmiana fragmentu lub trybu startowego (klucz) zeruje rozwinięty kontekst i tryb dokumentu. */
function EvidenceBody({
  target,
  footerLabel,
  initialMode,
}: {
  target: EvidenceTarget;
  footerLabel: string | null;
  initialMode: "window" | "document";
}) {
  const t = useT();
  const [before, setBefore] = useState(DEFAULT_CONTEXT_CHUNKS);
  const [after, setAfter] = useState(DEFAULT_CONTEXT_CHUNKS);
  const [mode, setMode] = useState<"window" | "document">(initialMode);
  const [attempt, setAttempt] = useState(0);
  const [loadedMeta, setLoadedMeta] = useState<EvidenceMeta | null>(null);
  const retry = () => setAttempt((value) => value + 1);
  const handleMeta = useCallback((meta: EvidenceMeta) => {
    setLoadedMeta(meta);
  }, []);

  const snapshotId = loadedMeta?.snapshotId ?? target.snapshotId;
  const isSynthetic = loadedMeta?.isSynthetic ?? target.isSynthetic ?? false;
  const docDate = loadedMeta?.docDate ?? target.docDate ?? null;
  const productVersion =
    loadedMeta?.productVersion ?? target.productVersion ?? null;
  const resolvedTarget =
    snapshotId === target.snapshotId ? target : { ...target, snapshotId };

  const meta: string[] = [];
  if (target.headings.length > 0) meta.push(target.headings.join(" › "));

  const dateText = docDate
    ? `${t("evidence.docDate")}: ${docDate}${
        isSynthetic ? ` (${t("conflict.syntheticDateTag")})` : ""
      }`
    : t("evidence.unknownDate");

  return (
    <>
      {target.claims.length > 0 ? (
        <div className="flex flex-col gap-2 px-[16px] pt-2 md:px-6">
          {target.claims.map((claim) => (
            <div
              key={claim.index}
              className="py-0.5 pl-3 shadow-[inset_3px_0_0_var(--color-accent)]"
            >
              <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-accent-strong uppercase">
                {claim.label
                  ? claim.label
                  : target.sideLabel
                    ? t("evidence.conflictFooter", { side: target.sideLabel })
                    : t("evidence.supports", { n: claim.index })}
              </div>
              <div className="text-sm leading-5">{claim.text}</div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="px-[16px] pt-2.5 md:px-6">
        <div className="flex flex-wrap items-start gap-2">
          <div className="line-clamp-2 min-w-0 flex-1 text-[15px] leading-[22px] font-semibold">
            {target.title}
          </div>
          {isSynthetic ? (
            <span
              title={t("conflict.syntheticTooltip")}
              className="inline-flex flex-none cursor-help items-center gap-1 rounded-md bg-chip px-2 py-px text-xs leading-5 font-semibold tracking-[.04em] whitespace-nowrap text-chip-text"
            >
              {t("conflict.syntheticBadge")}
              <InfoIcon size={13} />
            </span>
          ) : null}
        </div>
        <div className="mt-0.5 text-xs leading-[18px] text-muted">
          <span className="font-mono">{target.docId}</span>
          {meta.map((part) => (
            <span key={part}> · {part}</span>
          ))}
          {" · "}
          {dateText}
          {productVersion ? (
            <>
              {" · "}
              {t("evidence.productVersion")}: {productVersion}
            </>
          ) : null}
          {" · "}
          {t("evidence.snapshot")}{" "}
          <span className="font-mono">{snapshotShort(snapshotId)}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-[16px] pt-3.5 pb-3 md:px-6">
        {mode === "window" ? (
          <WindowView
            target={target}
            before={before}
            after={after}
            attempt={attempt}
            onMeta={handleMeta}
            onMoreBefore={() =>
              setBefore((value) => Math.min(value + 1, MAX_CONTEXT_CHUNKS))
            }
            onMoreAfter={() =>
              setAfter((value) => Math.min(value + 1, MAX_CONTEXT_CHUNKS))
            }
            onRetry={retry}
          />
        ) : (
          <DocumentView
            target={resolvedTarget}
            attempt={attempt}
            onRetry={retry}
          />
        )}
      </div>

      <div className="flex items-center justify-between border-t border-border-soft px-[16px] py-2.5 md:px-6">
        <button
          type="button"
          onClick={() => setMode(mode === "window" ? "document" : "window")}
          className={FOOTER_BUTTON}
        >
          {mode === "window" ? (
            <Icon size={14}>
              <path d="M5 12h14M13 6l6 6-6 6" />
            </Icon>
          ) : (
            <Icon size={14}>
              <path d="M19 12H5M11 6l-6 6 6 6" />
            </Icon>
          )}
          {mode === "window"
            ? t("evidence.showDocument")
            : t("evidence.showWindow")}
        </button>
        {footerLabel ? (
          <span className="text-[13px] text-muted">{footerLabel}</span>
        ) : null}
      </div>
    </>
  );
}

/**
 * Panel dowodu (S1A): fragment z oknem kontekstu i całym dokumentem na żądanie.
 * Używany dla cytatów odpowiedzi i dla sprawdzonych fragmentów przy abstencji.
 * Zamykanie klawiszem Escape obsługuje trasa (decyduje, gdzie wraca fokus).
 * Obudowę (`aside` albo arkusz) daje `PanelFrame` w `AssistantFrame`.
 */
export function EvidencePanel({
  position,
  footerLabel,
  labels,
  target,
  initialMode = "window",
  onPrev,
  onNext,
  onClose,
}: {
  /** Np. „Źródło 3 z 3”. */
  position: string;
  footerLabel: string | null;
  labels: {
    prev: TranslationKey;
    next: TranslationKey;
    close: TranslationKey;
  };
  target: EvidenceTarget;
  /** Tryb początkowy panelu: okno kontekstu (domyślnie) albo od razu cały dokument. */
  initialMode?: "window" | "document";
  /** `undefined` wyłącza przycisk (brak poprzedniego/następnego). */
  onPrev?: () => void;
  onNext?: () => void;
  onClose: () => void;
}) {
  const t = useT();
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Otwarcie panelu przenosi fokus do niego, by Escape i Tab działały od razu.
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
      <div className="flex items-center justify-between px-[16px] pt-5 md:pt-2.5 md:pr-3 md:pl-6">
        <h2
          ref={headingRef}
          tabIndex={-1}
          aria-live="polite"
          className="m-0 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase"
        >
          {position}
        </h2>
        <div className="flex">
          <button
            type="button"
            aria-label={t(labels.prev)}
            title={t(labels.prev)}
            disabled={!onPrev}
            onClick={onPrev}
            className={NAV_BUTTON}
          >
            <ChevronIcon direction="left" />
          </button>
          <button
            type="button"
            aria-label={t(labels.next)}
            title={t(labels.next)}
            disabled={!onNext}
            onClick={onNext}
            className={NAV_BUTTON}
          >
            <ChevronIcon direction="right" />
          </button>
          <button
            type="button"
            aria-label={t(labels.close)}
            title={t(labels.close)}
            onClick={onClose}
            className={NAV_BUTTON}
          >
            <CloseIcon />
          </button>
        </div>
      </div>
      <EvidenceBody
        key={`${target.chunkId}:${initialMode}`}
        target={target}
        footerLabel={footerLabel}
        initialMode={initialMode}
      />
    </div>
  );
}
