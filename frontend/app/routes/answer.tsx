import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentProps,
} from "react";
import { useParams } from "react-router";

import { getAnswer, type CheckedChunk } from "../api/answers";
import { AbstentionView } from "../components/assistant/AbstentionView";
import { AnswerView } from "../components/assistant/AnswerView";
import { AssistantFrame } from "../components/assistant/AssistantFrame";
import {
  CHECKED_PREVIEW,
  CheckedChunksPanel,
} from "../components/assistant/CheckedChunksPanel";
import {
  Composer,
  type ComposerHandle,
} from "../components/assistant/Composer";
import { ConflictView } from "../components/assistant/ConflictView";
import { AnswerNotFound, ErrorState } from "../components/assistant/ErrorState";
import {
  EvidencePanel,
  type EvidenceTarget,
} from "../components/assistant/EvidencePanel";
import { ProgressCard } from "../components/assistant/ProgressCard";
import { QuestionBubble } from "../components/assistant/QuestionBubble";
import { useAsk } from "../components/assistant/useAsk";
import { useT } from "../i18n/context";
import { deriveSteps } from "../lib/stages";
import { useRemote } from "../lib/use-remote";

export function meta() {
  return [{ title: "KnowledgeOps" }];
}

/** Przywraca fokus po wyrenderowaniu zmiany (panel znika albo zamienia się innym). */
function focusSoon(find: () => HTMLElement | null | undefined) {
  requestAnimationFrame(() => find()?.focus());
}

/** Trasa `/odpowiedz/:id`: zapisana odpowiedź (1A), abstencja (1C) albo stan błędu. */
export default function AnswerRoute() {
  const { id } = useParams();
  // Klucz zeruje stan panelu i pobrania przy przejściu do innej odpowiedzi.
  return <AnswerScreen key={id} id={id ?? ""} />;
}

function AnswerScreen({ id }: { id: string }) {
  const t = useT();
  const { state: askState, ask } = useAsk();
  const composerRef = useRef<ComposerHandle>(null);

  const [attempt, setAttempt] = useState(0);
  const load = useCallback(
    (signal: AbortSignal) => {
      void attempt; // ponowienie = nowe żądanie
      return getAnswer(id, signal);
    },
    [id, attempt],
  );
  const remote = useRemote(load);

  // Panel dowodu odpowiedzi (stan klienta, niezapisywany).
  const [activeN, setActiveN] = useState<number | null>(null);
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const [activeSide, setActiveSide] = useState<"A" | "B" | null>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);

  // Panel sprawdzonych fragmentów (abstencja).
  const [checkedOpen, setCheckedOpen] = useState(false);
  const [showAllChecked, setShowAllChecked] = useState(false);
  const [chunkIndex, setChunkIndex] = useState<number | null>(null);
  const checkedButtonRef = useRef<HTMLButtonElement>(null);

  const record = remote.status === "ready" ? remote.data : null;
  const result = record?.result ?? null;
  const answered = result?.outcome === "answered" ? result : null;
  const abstained = result?.outcome === "abstained" ? result : null;
  const conflicting = result?.outcome === "conflicting" ? result : null;
  const total = answered?.citations.length ?? 0;
  const checkedChunks: CheckedChunk[] = abstained?.checked_chunks ?? [];

  const openCitation = useCallback((n: number, trigger?: HTMLElement) => {
    if (trigger) lastTrigger.current = trigger;
    setActiveN(n);
    setOpened((previous) => new Set(previous).add(n));
  }, []);

  const closeCitation = useCallback(() => {
    const n = activeN;
    setActiveN(null);
    if (n === null) return;
    focusSoon(() => {
      const trigger = lastTrigger.current;
      if (trigger?.isConnected && trigger.dataset.citation === String(n)) {
        return trigger;
      }
      return document.querySelector<HTMLElement>(
        `button[data-citation="${n}"]`,
      );
    });
  }, [activeN]);

  const openSide = useCallback((side: "A" | "B", trigger?: HTMLElement) => {
    if (trigger) lastTrigger.current = trigger;
    setActiveSide(side);
  }, []);

  const closeSide = useCallback(() => {
    const side = activeSide;
    setActiveSide(null);
    if (side === null) return;
    focusSoon(() => {
      const trigger = lastTrigger.current;
      if (trigger?.isConnected) return trigger;
      return document.querySelector<HTMLElement>(
        `button[data-conflict-side="${side}"]`,
      );
    });
  }, [activeSide]);

  const openBothSides = useCallback(
    (trigger: HTMLElement) => {
      openSide(activeSide === "A" ? "B" : "A", trigger);
    },
    [activeSide, openSide],
  );

  const refineConflict = useCallback(() => {
    if (!record || !conflicting) return;
    const text = conflicting.refine_hint
      ? `${record.question} (${conflicting.refine_hint})`
      : record.question;
    composerRef.current?.focusWith(text);
  }, [record, conflicting]);

  /** „Otwórz wszystkie cytaty”: kolejny nieotwarty cytat (po komplecie od początku). */
  const openNext = useCallback(
    (trigger: HTMLElement) => {
      let next = 1;
      while (next <= total && opened.has(next)) next += 1;
      openCitation(next > total ? 1 : next, trigger);
    },
    [opened, total, openCitation],
  );

  const closeChunk = useCallback(() => {
    const index = chunkIndex;
    setChunkIndex(null);
    if (index === null) return;
    // Fragment dojrzany strzałkami może leżeć poza podglądem pierwszych pozycji.
    if (index >= CHECKED_PREVIEW) setShowAllChecked(true);
    focusSoon(() =>
      document.querySelector<HTMLElement>(`[data-chunk-index="${index}"]`),
    );
  }, [chunkIndex]);

  const closeChecked = useCallback(() => {
    setCheckedOpen(false);
    focusSoon(() => checkedButtonRef.current);
  }, []);

  const panelOpen = activeN !== null || activeSide !== null || checkedOpen;
  const onEscape = useCallback(() => {
    if (activeN !== null) closeCitation();
    else if (activeSide !== null) closeSide();
    else if (chunkIndex !== null) closeChunk();
    else closeChecked();
  }, [
    activeN,
    activeSide,
    chunkIndex,
    closeCitation,
    closeSide,
    closeChunk,
    closeChecked,
  ]);

  useEffect(() => {
    if (!panelOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        onEscape();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [panelOpen, onEscape]);

  // --- Panel boczny ---
  let panel = null;
  let panelFrame: ComponentProps<typeof AssistantFrame>["panelFrame"];
  if (answered && record && activeN !== null) {
    const citation = answered.citations.find((c) => c.n === activeN);
    if (citation) {
      const target: EvidenceTarget = {
        chunkId: citation.chunk_id,
        snapshotId: citation.snapshot_id ?? record.snapshot_id,
        docId: citation.doc_id,
        title: citation.title,
        headings: citation.headings,
        quotes: citation.claims.map((c) => ({
          start: c.quote_start,
          end: c.quote_end,
        })),
        claims: citation.claims.map((c) => ({
          index: c.claim_index + 1,
          text: answered.claims[c.claim_index]?.text ?? c.quote,
        })),
        isSynthetic: citation.is_synthetic,
        docDate: citation.doc_date,
        productVersion: citation.product_version,
      };
      panel = (
        <EvidencePanel
          position={t("evidence.source", { n: activeN, total })}
          footerLabel={t("citation.label", { n: activeN, total })}
          labels={{
            prev: "evidence.prev",
            next: "evidence.next",
            close: "evidence.close",
          }}
          target={target}
          onPrev={activeN > 1 ? () => openCitation(activeN - 1) : undefined}
          onNext={activeN < total ? () => openCitation(activeN + 1) : undefined}
          onClose={closeCitation}
        />
      );
      panelFrame = {
        label: t("evidence.panel"),
        variant: "evidence",
        onDismiss: closeCitation,
      };
    }
  } else if (conflicting && record && activeSide !== null) {
    const side =
      conflicting.sides.find((item) => item.label === activeSide) ??
      conflicting.sides[0];
    const sideNumber = side.label === "A" ? 1 : 2;
    const target: EvidenceTarget = {
      chunkId: side.chunk_id,
      snapshotId: side.snapshot_id || record.snapshot_id,
      docId: side.doc_id,
      title: side.title,
      headings: side.headings,
      quotes:
        side.quote_end > side.quote_start
          ? [{ start: side.quote_start, end: side.quote_end }]
          : [],
      claims: [{ index: sideNumber, text: side.claim_text }],
      isSynthetic: side.is_synthetic,
      docDate: side.doc_date,
      productVersion: side.product_version,
      sideLabel: side.label,
    };
    panel = (
      <EvidencePanel
        position={t("evidence.conflictSide", {
          side: side.label,
          n: sideNumber,
          total: 2,
        })}
        footerLabel={t("evidence.conflictFooter", { side: side.label })}
        labels={{
          prev: "evidence.prevSource",
          next: "evidence.nextSource",
          close: "evidence.close",
        }}
        target={target}
        onPrev={side.label === "B" ? () => openSide("A") : undefined}
        onNext={side.label === "A" ? () => openSide("B") : undefined}
        onClose={closeSide}
      />
    );
    panelFrame = {
      label: t("evidence.panel"),
      variant: "evidence",
      onDismiss: closeSide,
    };
  } else if (abstained && record && checkedOpen) {
    const chunk = chunkIndex === null ? null : checkedChunks[chunkIndex];
    if (chunkIndex !== null && chunk) {
      const target: EvidenceTarget = {
        chunkId: chunk.chunk_id,
        snapshotId: record.snapshot_id,
        docId: chunk.doc_id,
        title: chunk.title,
        headings: chunk.headings,
        quotes: [],
        claims: [],
      };
      panel = (
        <EvidencePanel
          position={t("evidence.fragment", {
            n: chunkIndex + 1,
            total: checkedChunks.length,
          })}
          footerLabel={null}
          labels={{
            prev: "evidence.prevChunk",
            next: "evidence.nextChunk",
            close: "evidence.close",
          }}
          target={target}
          onPrev={
            chunkIndex > 0 ? () => setChunkIndex(chunkIndex - 1) : undefined
          }
          onNext={
            chunkIndex < checkedChunks.length - 1
              ? () => setChunkIndex(chunkIndex + 1)
              : undefined
          }
          onClose={closeChunk}
        />
      );
      // Wariant `checked` także dla fragmentu: szeroki panel nie zmienia szerokości.
      panelFrame = {
        label: t("evidence.panel"),
        variant: "checked",
        onDismiss: closeChunk,
      };
    } else {
      panel = (
        <CheckedChunksPanel
          chunks={checkedChunks}
          showAll={showAllChecked}
          onShowAll={() => setShowAllChecked(true)}
          onOpen={(index) => setChunkIndex(index)}
          onClose={closeChecked}
        />
      );
      panelFrame = {
        label: t("checked.panel"),
        variant: "checked",
        onDismiss: closeChecked,
      };
    }
  }

  // --- Treść ---
  let thread;
  if (askState.status === "asking") {
    thread = (
      <>
        <QuestionBubble question={askState.question} />
        <ProgressCard steps={deriveSteps(askState.stages)} />
      </>
    );
    panel = null;
    panelFrame = undefined;
  } else if (askState.status === "failed") {
    const { question, error } = askState;
    thread = (
      <>
        <QuestionBubble question={question} />
        <ErrorState code={error.code} onRetry={() => ask(question)} />
      </>
    );
    panel = null;
    panelFrame = undefined;
  } else if (remote.status === "loading") {
    thread = (
      <p role="status" className="m-0 text-[15px] leading-6 text-muted">
        {t("answer.loading")}
      </p>
    );
  } else if (remote.status === "not_found") {
    thread = <AnswerNotFound />;
  } else if (remote.status === "error" || !record || !result) {
    thread = (
      <ErrorState code="internal" onRetry={() => setAttempt((v) => v + 1)} />
    );
  } else if (answered) {
    thread = (
      <>
        <QuestionBubble question={record.question} />
        <AnswerView
          record={record}
          result={answered}
          activeN={activeN}
          opened={opened}
          onOpen={openCitation}
          onOpenAll={openNext}
        />
      </>
    );
  } else if (conflicting) {
    thread = (
      <>
        <QuestionBubble question={record.question} />
        <ConflictView
          record={record}
          result={conflicting}
          activeSide={activeSide}
          onOpenSide={openSide}
          onOpenBoth={openBothSides}
          onRefine={refineConflict}
        />
      </>
    );
  } else if (abstained) {
    thread = (
      <>
        <QuestionBubble question={record.question} />
        <AbstentionView
          record={record}
          result={abstained}
          checkedOpen={checkedOpen}
          checkedButtonRef={checkedButtonRef}
          onRefine={() => composerRef.current?.focusWith(record.question)}
          onToggleChecked={() => {
            if (checkedOpen) {
              closeChecked();
            } else {
              setCheckedOpen(true);
            }
          }}
        />
      </>
    );
  } else {
    // Odpowiedź `failed`: pytanie i stan błędu z ponowieniem.
    const { question } = record;
    thread = (
      <>
        <QuestionBubble question={question} />
        <ErrorState code="internal" onRetry={() => ask(question)} />
      </>
    );
  }

  const placeholder =
    askState.status === "idle" && (abstained || conflicting)
      ? t("composer.placeholderRefine")
      : t("composer.placeholder");

  return (
    <AssistantFrame
      thread={thread}
      panel={panel}
      panelFrame={panelFrame}
      composer={
        <Composer
          ref={composerRef}
          onSubmit={ask}
          busy={askState.status === "asking"}
          placeholder={placeholder}
        />
      }
    />
  );
}
