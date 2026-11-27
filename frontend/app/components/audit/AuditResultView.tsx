import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import type {
  AuditClaimResponse,
  AuditDetailResponse,
  ClaimVerdict,
  NoteVerdict,
} from "../../api/audits";
import { useLanguage, useT } from "../../i18n/context";
import {
  buildNoteSegments,
  CLAIM_VERDICT_LABEL,
  claimTag,
  hasSyntheticScope,
  NOTE_VERDICT_LABEL,
} from "../../lib/audit";
import { pluralForm } from "../../lib/plural";
import { snapshotShort } from "../../lib/snapshot";
import { EvidencePanel, type EvidenceTarget } from "../assistant/EvidencePanel";
import {
  ChevronIcon,
  ContradictionIcon,
  ExternalLinkIcon,
  InfoIcon,
  InsufficientIcon,
  PartialIcon,
  SupportedIcon,
  SystemIcon,
} from "../assistant/Icon";
import { PanelFrame } from "../assistant/PanelFrame";
import { AuditPreparationDetails } from "./AuditPreparationDetails";
import { CaseContextPanel } from "./CaseContextPanel";

type ActivePanel =
  | null
  | { kind: "context" }
  | {
      kind: "evidence";
      claimId: string;
      evidenceIndex: number;
      initialMode: "window" | "document";
    };

function focusSoon(find: () => HTMLElement | null | undefined) {
  requestAnimationFrame(() => find()?.focus());
}

/** Pigułka oceny całej notatki (zawsze słowo i ikona; brak dowodu szary, nigdy czerwony). */
function NoteVerdictPill({ verdict }: { verdict: NoteVerdict }) {
  const t = useT();
  const styles: Record<NoteVerdict, string> = {
    full: "bg-supported-bg text-supported-text",
    partial: "bg-partial-bg text-partial-text",
    contradiction: "bg-conflict-bg text-conflict-text",
    insufficient: "bg-insufficient-bg text-insufficient-text",
  };
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full py-[3px] pr-3 pl-2.5 text-[13px] leading-[22px] font-semibold whitespace-nowrap " +
        styles[verdict]
      }
    >
      {verdict === "full" ? (
        <SupportedIcon size={14} className="flex-none text-supported-icon" />
      ) : verdict === "partial" ? (
        <PartialIcon size={15} className="flex-none text-partial-icon" />
      ) : verdict === "contradiction" ? (
        <ContradictionIcon size={14} className="flex-none text-conflict-icon" />
      ) : (
        <InsufficientIcon size={15} className="flex-none text-icon" />
      )}
      {t(NOTE_VERDICT_LABEL[verdict])}
    </span>
  );
}

/** Pigułka oceny pojedynczej tezy (zawsze słowo i ikona; brak dowodu szary). */
function ClaimVerdictPill({
  verdict,
  size = "sm",
}: {
  verdict: ClaimVerdict;
  size?: "sm" | "md";
}) {
  const t = useT();
  const styles: Record<ClaimVerdict, string> = {
    supported: "bg-supported-bg text-supported-text",
    contradicted: "bg-conflict-bg text-conflict-text",
    insufficient: "bg-insufficient-bg text-insufficient-text",
  };
  const textSize = size === "md" ? "text-sm" : "text-xs";
  const iconSize = size === "md" ? 16 : 14;
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full py-[3px] pr-3 pl-2.5 leading-[22px] font-semibold whitespace-nowrap " +
        textSize +
        " " +
        styles[verdict]
      }
    >
      {verdict === "supported" ? (
        <SupportedIcon
          size={iconSize}
          className="flex-none text-supported-icon"
        />
      ) : verdict === "contradicted" ? (
        <ContradictionIcon
          size={iconSize}
          className="flex-none text-conflict-icon"
        />
      ) : (
        <InsufficientIcon size={iconSize} className="flex-none text-icon" />
      )}
      {t(CLAIM_VERDICT_LABEL[verdict])}
    </span>
  );
}

function ClaimTagBadge({ tag, selected }: { tag: string; selected: boolean }) {
  return (
    <span
      className={
        "inline-flex h-5 flex-none items-center justify-center rounded-[5px] px-1.5 font-sans text-xs font-semibold " +
        (selected
          ? "bg-primary text-white"
          : "bg-white text-text shadow-[inset_0_0_0_1px_var(--color-border)]")
      }
    >
      {tag}
    </span>
  );
}

function underlineClass(verdict: ClaimVerdict): string {
  if (verdict === "supported") {
    return "underline decoration-supported-underline decoration-solid decoration-2 underline-offset-[5px]";
  }
  if (verdict === "contradicted") {
    return "underline decoration-conflict-icon decoration-solid decoration-2 underline-offset-[5px]";
  }
  return "underline decoration-muted decoration-dashed decoration-2 underline-offset-[5px]";
}

/**
 * Ekran wyniku audytu (3 na desktopie, 3N w wąskim oknie 390 px bez przewijania w poziomie).
 * Zakres S-08: ocena systemu, podświetlana notatka, lista tez, panel dowodu i kontekst sprawy
 * (bez panelu decyzji redaktora z S-09 i bez listy analiz z S-10).
 */
export function AuditResultView({ audit }: { audit: AuditDetailResponse }) {
  const t = useT();
  const { lang } = useLanguage();

  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(
    audit.claims[0]?.claim_id ?? null,
  );
  const [activePanel, setActivePanel] = useState<ActivePanel>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const contextButtonRef = useRef<HTMLButtonElement>(null);

  const selectedClaim: AuditClaimResponse | null =
    audit.claims.find((claim) => claim.claim_id === selectedClaimId) ??
    audit.claims[0] ??
    null;

  const closePanel = useCallback(() => {
    const current = activePanel;
    setActivePanel(null);
    if (!current) return;
    if (current.kind === "context") {
      focusSoon(() => contextButtonRef.current);
      return;
    }
    focusSoon(() =>
      lastTrigger.current?.isConnected ? lastTrigger.current : null,
    );
  }, [activePanel]);

  useEffect(() => {
    if (!activePanel) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        closePanel();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [activePanel, closePanel]);

  const selectClaim = useCallback((claimId: string) => {
    setSelectedClaimId(claimId);
    // Zmiana tezy zamyka otwarty panel dowodu dla poprzedniej tezy.
    setActivePanel((prev) =>
      prev?.kind === "evidence" && prev.claimId !== claimId ? null : prev,
    );
  }, []);

  const openEvidence = useCallback(
    (
      claimId: string,
      evidenceIndex: number,
      initialMode: "window" | "document",
      trigger?: HTMLElement,
    ) => {
      if (trigger) lastTrigger.current = trigger;
      setActivePanel({
        kind: "evidence",
        claimId,
        evidenceIndex,
        initialMode,
      });
    },
    [],
  );

  const toggleContextPanel = useCallback(() => {
    setActivePanel((prev) =>
      prev?.kind === "context" ? null : { kind: "context" },
    );
  }, []);

  const noteSegments = buildNoteSegments(audit.resolution_note, audit.claims);
  const missingCount = audit.case_context?.missing_info.length ?? 0;
  const missingLabel =
    missingCount > 0
      ? t(`audit.detail.missingInfo${pluralForm(lang, missingCount)}`, {
          n: missingCount,
        })
      : t("audit.detail.missingInfoNone");

  const syntheticScope = hasSyntheticScope(audit);
  const shortSnapshot = snapshotShort(audit.snapshot_id);
  const noteVerdict: NoteVerdict = audit.note_verdict ?? "insufficient";

  // --- Wspólny slot panelu bocznego (EvidencePanel albo CaseContextPanel) ---
  let sidePanel = null;
  if (activePanel?.kind === "context") {
    sidePanel = (
      <PanelFrame
        label={t("audit.context.panelLabel")}
        variant="checked"
        onDismiss={closePanel}
      >
        <CaseContextPanel
          caseContext={audit.case_context}
          caseDescription={audit.case_description}
          onClose={closePanel}
        />
      </PanelFrame>
    );
  } else if (activePanel?.kind === "evidence") {
    const panelClaim = audit.claims.find(
      (item) => item.claim_id === activePanel.claimId,
    );
    const evidenceItem = panelClaim?.evidence[activePanel.evidenceIndex];
    if (panelClaim && evidenceItem) {
      const total = panelClaim.evidence.length;
      const tag = claimTag(panelClaim.claim_index);
      const evidenceClaimLabel =
        panelClaim.verdict === "supported" && evidenceItem.supports_claim
          ? t("audit.detail.evidenceLabelSupported", { tag })
          : panelClaim.verdict === "contradicted"
            ? t("audit.detail.evidenceLabelContradicted", { tag })
            : t("audit.detail.evidenceLabelClosest", { tag });
      const target: EvidenceTarget = {
        chunkId: evidenceItem.chunk_id,
        snapshotId: evidenceItem.snapshot_id ?? audit.snapshot_id,
        docId: evidenceItem.document_id,
        title: evidenceItem.document_title,
        headings: [],
        quotes:
          evidenceItem.quote_end > evidenceItem.quote_start
            ? [
                {
                  start: evidenceItem.quote_start,
                  end: evidenceItem.quote_end,
                },
              ]
            : [],
        claims: [
          {
            index: panelClaim.claim_index + 1,
            text: panelClaim.claim_text,
            label: evidenceClaimLabel,
          },
        ],
        isSynthetic: evidenceItem.is_synthetic,
      };
      sidePanel = (
        <PanelFrame
          label={t("evidence.panel")}
          variant="evidence"
          onDismiss={closePanel}
        >
          <EvidencePanel
            position={t("audit.detail.evidencePosition", {
              n: activePanel.evidenceIndex + 1,
              total,
              tag,
            })}
            footerLabel={t("audit.detail.evidenceFooter", { tag })}
            labels={{
              prev: "evidence.prevChunk",
              next: "evidence.nextChunk",
              close: "evidence.close",
            }}
            target={target}
            initialMode={activePanel.initialMode}
            onPrev={
              activePanel.evidenceIndex > 0
                ? () =>
                    setActivePanel({
                      ...activePanel,
                      evidenceIndex: activePanel.evidenceIndex - 1,
                    })
                : undefined
            }
            onNext={
              activePanel.evidenceIndex < total - 1
                ? () =>
                    setActivePanel({
                      ...activePanel,
                      evidenceIndex: activePanel.evidenceIndex + 1,
                    })
                : undefined
            }
            onClose={closePanel}
          />
        </PanelFrame>
      );
    }
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Nagłówek sprawy + ocena całej notatki */}
        <div className="flex flex-none flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b border-border-soft px-4 py-3 md:px-6 lg:px-8 lg:py-3.5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-xs leading-[18px] text-muted">
              <Link
                to="/audyt"
                className="text-muted no-underline hover:underline"
              >
                {t("audit.detail.newAudit")}
              </Link>
              <span aria-hidden="true">·</span>
              <span>
                {t("audit.detail.wholeSnapshot", { snapshot: shortSnapshot })}
              </span>
              {syntheticScope ? (
                <span>{t("audit.detail.syntheticIncluded")}</span>
              ) : null}
            </div>
            <h1 className="m-0 mt-0.5 text-lg leading-7 font-semibold [overflow-wrap:anywhere] lg:text-[22px] lg:leading-[30px]">
              {audit.case_ref
                ? t("audit.detail.titleWithRef", { ref: audit.case_ref })
                : t("audit.detail.titleDefault")}
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <SystemIcon size={14} className="flex-none text-muted" />
            <span>{t("audit.detail.noteVerdictLabel")}</span>
            <NoteVerdictPill verdict={noteVerdict} />
          </div>
        </div>

        {/* Treść: lewa kolumna (notatka + lista tez + kontekst) i środkowa (ocena systemu) */}
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
          <section className="flex flex-col border-b border-border-soft px-4 py-4 md:px-6 lg:w-[400px] lg:flex-none lg:overflow-hidden lg:border-r lg:border-b-0 lg:px-7 lg:pt-6 lg:pb-3 xl:w-[440px]">
            <div className="flex-none">
              <div className="mb-2 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
                {t("audit.detail.noteHeading")}
              </div>
              <div className="font-serif text-base leading-8 [overflow-wrap:anywhere] lg:text-[17px] lg:leading-[34px]">
                {noteSegments.map((segment, index) => {
                  if (segment.kind === "text") {
                    return <span key={index}>{segment.text}</span>;
                  }
                  const isSelected =
                    selectedClaim?.claim_id === segment.claimId;
                  const tag = claimTag(segment.claimIndex);
                  return (
                    <span
                      key={segment.claimId}
                      role="button"
                      tabIndex={0}
                      onClick={() => selectClaim(segment.claimId)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          selectClaim(segment.claimId);
                        }
                      }}
                      className={
                        "cursor-pointer rounded-[3px] px-0.5 py-px [box-decoration-break:clone] " +
                        underlineClass(segment.verdict) +
                        (isSelected ? " bg-claim-selected" : "")
                      }
                    >
                      <span className="mr-1 inline-block align-[2px]">
                        <ClaimTagBadge tag={tag} selected={isSelected} />
                      </span>
                      {segment.text}
                    </span>
                  );
                })}
              </div>
            </div>

            <div className="mt-5 flex min-h-0 flex-1 flex-col">
              <div className="mb-1.5 flex-none text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
                {t("audit.detail.claimsHeading", { n: audit.claims.length })}
              </div>
              {audit.claims.length === 0 ? (
                <p className="m-0 text-sm leading-5 text-muted">
                  {t("audit.detail.noClaims")}
                </p>
              ) : (
                <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-0.5">
                  {audit.claims.map((claim) => {
                    const isSelected =
                      selectedClaim?.claim_id === claim.claim_id;
                    const tag = claimTag(claim.claim_index);
                    return (
                      <button
                        key={claim.claim_id}
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => selectClaim(claim.claim_id)}
                        className={
                          "flex w-full cursor-pointer items-start gap-2.5 rounded-lg border-0 px-2.5 py-2 text-left font-sans text-text " +
                          (isSelected
                            ? "bg-white shadow-[inset_0_0_0_1px_var(--color-border)]"
                            : "bg-transparent hover:bg-surface-alt")
                        }
                      >
                        <ClaimTagBadge tag={tag} selected={isSelected} />
                        <span className="min-w-0 flex-1">
                          <span
                            className={
                              "block text-sm leading-5 [overflow-wrap:anywhere] " +
                              (isSelected ? "font-semibold" : "font-normal")
                            }
                          >
                            {claim.claim_label}
                          </span>
                          <span className="mt-1 block">
                            <ClaimVerdictPill verdict={claim.verdict} />
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="mt-3 flex-none">
              <button
                ref={contextButtonRef}
                type="button"
                aria-expanded={activePanel?.kind === "context"}
                onClick={toggleContextPanel}
                className="flex w-full cursor-pointer items-center gap-2.5 border-0 border-t border-border-soft bg-transparent px-0.5 py-3 text-left font-sans text-sm text-text hover:bg-surface-alt"
              >
                <span className="flex-1 font-medium">
                  {t("audit.detail.caseContextButton")}
                </span>
                <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
                  <InfoIcon size={14} />
                  {missingLabel}
                </span>
                <span className="text-muted">
                  <ChevronIcon direction="right" size={16} />
                </span>
              </button>
            </div>
          </section>

          <section className="flex min-w-0 flex-1 flex-col px-4 py-5 md:px-6 lg:overflow-y-auto lg:px-8 lg:pt-5 lg:pb-4">
            <div className="flex flex-wrap items-center gap-2 border-b border-border-soft pb-2.5">
              <SystemIcon size={16} className="flex-none text-muted" />
              <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
                {t("audit.detail.systemRatingHeading")}
              </div>
              <span className="text-xs text-muted">
                · {t("audit.detail.systemRatingSub")}
              </span>
            </div>

            {selectedClaim ? (
              <ClaimAssessment
                claim={selectedClaim}
                shortSnapshot={shortSnapshot}
                syntheticScope={syntheticScope}
                onOpenEvidence={openEvidence}
              />
            ) : (
              <p className="mt-4 mb-0 text-sm leading-[22px] text-muted">
                {t("audit.detail.noClaims")}
              </p>
            )}

            <div className="mt-auto pt-5">
              <p className="mt-0 mb-3 flex items-start gap-2 text-xs leading-[18px] text-muted">
                <span className="mt-0.5 flex-none">
                  <InfoIcon size={14} />
                </span>
                <span>{t("audit.detail.doesNotChangeDocs")}</span>
              </p>
              <AuditPreparationDetails audit={audit} />
            </div>
          </section>
        </div>
      </div>

      {sidePanel}
    </div>
  );
}

function ClaimAssessment({
  claim,
  shortSnapshot,
  syntheticScope,
  onOpenEvidence,
}: {
  claim: AuditClaimResponse;
  shortSnapshot: string;
  syntheticScope: boolean;
  onOpenEvidence: (
    claimId: string,
    evidenceIndex: number,
    initialMode: "window" | "document",
    trigger?: HTMLElement,
  ) => void;
}) {
  const t = useT();
  const tag = claimTag(claim.claim_index);
  const topDoc = claim.checked_docs[0] ?? null;

  const evidenceHeadingKey =
    claim.verdict === "supported"
      ? "audit.detail.evidenceSupportedHeading"
      : claim.verdict === "contradicted"
        ? "audit.detail.evidenceContradictedHeading"
        : "audit.detail.evidenceClosestHeading";

  return (
    <div className="mt-3.5 max-w-[680px]">
      <div className="flex flex-wrap items-center gap-2.5">
        <ClaimTagBadge tag={tag} selected />
        <h2 className="m-0 text-[15px] leading-[22px] font-semibold [overflow-wrap:anywhere]">
          {claim.claim_label}
        </h2>
        <ClaimVerdictPill verdict={claim.verdict} size="md" />
      </div>

      {claim.claim_text.trim() !== claim.claim_label.trim() ? (
        <p className="mt-2.5 mb-0 text-base leading-6 font-medium [overflow-wrap:anywhere] text-text">
          {claim.claim_text}
        </p>
      ) : null}

      <p className="mt-2 mb-0 text-sm leading-[22px] [overflow-wrap:anywhere] text-secondary">
        {claim.rationale}
      </p>

      {claim.scope_note ? (
        <p className="mt-2 mb-0 text-[13px] leading-5 [overflow-wrap:anywhere] text-muted">
          {claim.scope_note}
        </p>
      ) : null}

      {claim.verdict === "insufficient" ? (
        <p className="mt-2.5 mb-0 flex items-start gap-2 text-[13px] leading-5 text-muted">
          <span className="mt-0.5 flex-none">
            <InfoIcon size={14} />
          </span>
          <span>{t("audit.detail.insufficientCaveat")}</span>
        </p>
      ) : null}

      {claim.error ? (
        <p className="mt-2 mb-0 flex items-start gap-2 rounded-lg bg-surface px-3 py-2 text-[13px] leading-5 text-secondary">
          <span className="mt-0.5 flex-none text-muted">
            <InfoIcon size={14} />
          </span>
          <span>{t("audit.detail.claimErrorNote")}</span>
        </p>
      ) : null}

      <div className="mt-2.5 text-xs leading-[18px] text-muted">
        {t("audit.detail.checkedScope")}{" "}
        {topDoc ? (
          <>
            <span className="font-mono">{topDoc.source_doc_id}</span>{" "}
            {t("audit.detail.closestLabel")} ·{" "}
          </>
        ) : null}
        {t("audit.detail.wholeSnapshot", { snapshot: shortSnapshot })}
        {syntheticScope ? <> · {t("audit.detail.syntheticIncluded")}</> : null}
      </div>

      <div className="mt-5 flex flex-col gap-5">
        {claim.evidence.length > 0 ? (
          claim.evidence.map((ev, index) => {
            const statusChipKey =
              ev.supports_claim && claim.verdict === "supported"
                ? "audit.detail.evidenceSupports"
                : claim.verdict === "contradicted"
                  ? "audit.detail.evidenceContradicts"
                  : "audit.detail.evidenceDoesNotSupport";
            return (
              <div key={`${ev.chunk_id}-${index}`}>
                <div className="flex flex-wrap items-center gap-2.5">
                  <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
                    {t(evidenceHeadingKey)}
                  </div>
                  <span className="text-xs text-muted">
                    <span className="font-mono">{ev.source_doc_id}</span>
                    {ev.document_title ? ` · ${ev.document_title}` : null}
                  </span>
                  {ev.is_synthetic ? (
                    <span
                      title={t("conflict.syntheticTooltip")}
                      className="inline-flex cursor-help items-center gap-1 rounded-md bg-chip px-2 py-px text-xs leading-5 font-semibold tracking-[.04em] whitespace-nowrap text-chip-text"
                    >
                      {t("conflict.syntheticBadge")}
                      <InfoIcon size={13} />
                    </span>
                  ) : null}
                  <span className="ml-auto inline-block rounded-md bg-surface px-2 py-px text-xs leading-5 font-medium whitespace-nowrap text-muted">
                    {t(statusChipKey)}
                  </span>
                </div>

                <div className="mt-2.5 py-0.5 pl-4 shadow-[inset_3px_0_0_var(--color-border)]">
                  <div className="font-serif text-base leading-[26px] [overflow-wrap:anywhere] whitespace-pre-wrap text-text">
                    {ev.quote}
                  </div>
                </div>

                <div className="mt-2.5 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={(event) =>
                      onOpenEvidence(
                        claim.claim_id,
                        index,
                        "window",
                        event.currentTarget,
                      )
                    }
                    className="inline-flex h-[34px] flex-none cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-surface px-3 font-sans text-[13px] font-medium whitespace-nowrap text-text hover:brightness-95"
                  >
                    <ChevronIcon direction="down" size={16} />
                    {t("audit.detail.showWiderContext")}
                  </button>
                  <button
                    type="button"
                    onClick={(event) =>
                      onOpenEvidence(
                        claim.claim_id,
                        index,
                        "document",
                        event.currentTarget,
                      )
                    }
                    className="inline-flex h-[34px] flex-none cursor-pointer items-center justify-center gap-2 rounded-lg border-0 bg-surface px-3 font-sans text-[13px] font-medium whitespace-nowrap text-text hover:brightness-95"
                  >
                    <ExternalLinkIcon size={16} />
                    {t("audit.detail.openFullDocument")}
                  </button>
                </div>
              </div>
            );
          })
        ) : (
          <p className="m-0 text-sm leading-[22px] text-muted">
            {t("audit.detail.noEvidenceFound")}
          </p>
        )}
      </div>
    </div>
  );
}
