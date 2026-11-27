import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../api/answers";
import {
  saveClaimDecision,
  type AuditClaimResponse,
  type AuditDetailResponse,
  type DecisionCategory,
} from "../../api/audits";
import { useLanguage, useT } from "../../i18n/context";
import {
  canSubmitDecision,
  CLAIM_VERDICT_LABEL,
  claimTag,
  DECISION_CATEGORIES,
  DECISION_CATEGORY_LABEL,
  formatAuditTimestamp,
  isDecisionUnchanged,
  MAX_JUSTIFICATION_LENGTH,
} from "../../lib/audit";
import { useRole } from "../../session/role";
import {
  CloseIcon,
  InfoIcon,
  PersonIcon,
  SupportedIcon,
} from "../assistant/Icon";

/**
 * Panel decyzji redaktora dla wybranej tezy (desktopowy prawy panel `3` oraz
 * mobilny arkusz `3N-D`). Brak domyślnego wyboru i brak „Sugestii systemu”.
 */
export function ClaimDecisionPanel({
  auditId,
  claim,
  onAuditChange,
  variant = "aside",
  onClose,
}: {
  auditId: string;
  claim: AuditClaimResponse;
  onAuditChange: (audit: AuditDetailResponse) => void;
  variant?: "aside" | "sheet";
  onClose?: () => void;
}) {
  const t = useT();
  const { lang } = useLanguage();
  const { role, setRole } = useRole();
  const textareaId = useId();
  const radioName = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [selectedCategory, setSelectedCategory] =
    useState<DecisionCategory | null>(claim.decision?.decision ?? null);
  const [justification, setJustification] = useState<string>(
    claim.decision?.justification ?? "",
  );
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  // Przeniesienie fokusu na nagłówek po otwarciu arkusza `3N-D`.
  useEffect(() => {
    if (variant === "sheet") {
      headingRef.current?.focus({ preventScroll: true });
    }
  }, [variant]);

  // Anulowanie żądania w locie przy odmontowaniu lub zmianie tezy (`key={claim.claim_id}`).
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  const tag = claimTag(claim.claim_index);
  const isSheet = variant === "sheet";
  const savedDecision = claim.decision ?? null;

  const canSubmit = canSubmitDecision(
    selectedCategory,
    justification,
    savedDecision,
    isSaving,
  );
  const unchanged = isDecisionUnchanged(
    selectedCategory,
    justification,
    savedDecision,
  );

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit || selectedCategory === null) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsSaving(true);
    setErrorMessage(null);
    setJustSaved(false);

    try {
      const trimmed = justification.trim();
      const updated = await saveClaimDecision(
        auditId,
        claim.claim_id,
        {
          decision: selectedCategory,
          justification: trimmed,
          role_label: role,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setJustification(trimmed);
      onAuditChange(updated);
      setJustSaved(true);
    } catch (error: unknown) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError) {
        if (error.status === 404) {
          setErrorMessage(t("audit.decision.errorNotFound"));
        } else if (error.status === 409) {
          setErrorMessage(t("audit.decision.errorNotCompleted"));
        } else if (error.status === 422) {
          setErrorMessage(t("audit.decision.errorValidation"));
        } else {
          setErrorMessage(t("audit.decision.errorGeneric"));
        }
      } else {
        setErrorMessage(t("audit.decision.errorGeneric"));
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsSaving(false);
      }
    }
  }

  let submitLabel: string;
  if (isSaving) {
    submitLabel = t("audit.decision.saving");
  } else if (!canSubmit && unchanged) {
    submitLabel = t("audit.decision.savedButton");
  } else if (!canSubmit) {
    submitLabel = t("audit.decision.incompleteButton");
  } else if (savedDecision) {
    submitLabel = t("audit.decision.updateButton", { tag });
  } else {
    submitLabel = t("audit.decision.saveButton", { tag });
  }

  const savedRoleLabel =
    savedDecision?.role_label === "consultant"
      ? t("header.roleConsultant")
      : t("header.roleEditor");

  return (
    <div
      className={
        isSheet
          ? "flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain bg-surface-alt px-4 pt-5 pb-4"
          : "flex min-h-0 flex-1 flex-col"
      }
    >
      {/* Nagłówek */}
      {isSheet ? (
        <div className="mb-3.5">
          <div className="flex items-center gap-2">
            <PersonIcon size={18} className="flex-none text-text" />
            <h2
              ref={headingRef}
              tabIndex={-1}
              className="m-0 text-base leading-6 font-semibold text-text"
            >
              {t("audit.decision.heading", { tag })}
            </h2>
            {onClose ? (
              <button
                type="button"
                aria-label={t("audit.decision.close")}
                title={t("audit.decision.close")}
                onClick={onClose}
                className="ml-auto inline-flex h-[40px] w-[40px] flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted hover:bg-surface"
              >
                <CloseIcon />
              </button>
            ) : null}
          </div>
          <div className="mt-1 flex items-center gap-2 text-[13px] leading-5 text-muted">
            <span className="inline-flex h-5 flex-none items-center justify-center rounded-[5px] bg-primary px-1.5 font-sans text-xs font-semibold text-white">
              {tag}
            </span>
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {claim.claim_label}
            </span>
          </div>
          <p className="mt-1 mb-0 text-[13px] leading-5 text-muted">
            {t("audit.decision.subtitleSheet", {
              verdict: t(CLAIM_VERDICT_LABEL[claim.verdict]).toLowerCase(),
            })}
          </p>
        </div>
      ) : (
        <div className="mb-3.5">
          <div className="flex items-center gap-2 text-[15px] leading-[22px] font-semibold text-text">
            <PersonIcon size={18} className="flex-none text-text" />
            <span>{t("audit.decision.heading", { tag })}</span>
          </div>
          <p className="mt-0.5 mb-0 text-[13px] leading-5 text-muted">
            {t("audit.decision.subtitle")}
          </p>
        </div>
      )}

      {/* Tryb read-only dla roli Konsultant */}
      {role === "consultant" ? (
        <div className="flex flex-col gap-3">
          {savedDecision ? (
            <div className="rounded-[10px] bg-white p-3.5 shadow-[inset_0_0_0_1px_var(--color-border)]">
              <div className="inline-flex items-center gap-1.5 rounded-full bg-supported-bg px-2.5 py-0.5 text-xs font-semibold text-supported-text">
                <SupportedIcon
                  size={12}
                  className="flex-none text-supported-icon"
                />
                {t("audit.decision.savedBadge")}
              </div>
              <div className="mt-2 text-sm leading-5 font-semibold text-text">
                {t(DECISION_CATEGORY_LABEL[savedDecision.decision])}
              </div>
              <p className="mt-1.5 mb-0 text-sm leading-[22px] [overflow-wrap:anywhere] whitespace-pre-wrap text-secondary">
                {savedDecision.justification}
              </p>
              <div className="mt-2 text-xs leading-[18px] text-muted">
                {t("audit.decision.lastSaved", {
                  role: savedRoleLabel,
                  time: formatAuditTimestamp(savedDecision.updated_at, lang),
                })}
              </div>
            </div>
          ) : null}

          <div className="rounded-[10px] bg-white p-3.5 shadow-[inset_0_0_0_1px_var(--color-border-soft)]">
            <p className="m-0 text-sm leading-5 text-secondary">
              {t("audit.decision.consultantReadOnly")}
            </p>
            <button
              type="button"
              onClick={() => setRole("editor")}
              className="mt-3 block h-10 w-full cursor-pointer rounded-lg border-0 bg-primary px-3 font-sans text-[13px] font-medium text-white hover:brightness-95"
            >
              {t("audit.decision.switchToEditor")}
            </button>
            <p className="mt-2.5 mb-0 text-xs leading-[18px] text-muted">
              {t("header.roleNotice")}
            </p>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
          className="flex flex-col"
        >
          <div
            role="radiogroup"
            aria-label={t("audit.decision.radioGroupLabel")}
            className="flex flex-col gap-1.5"
          >
            {DECISION_CATEGORIES.map((category) => {
              const checked = selectedCategory === category;
              return (
                <label
                  key={category}
                  className={
                    "relative flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-[10px] bg-white px-3.5 py-2.5 text-sm leading-5 text-text focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-focus " +
                    (checked
                      ? "font-medium shadow-[inset_0_0_0_2px_var(--color-primary)]"
                      : "shadow-[inset_0_0_0_1px_var(--color-border)] hover:bg-aside-soft")
                  }
                >
                  <input
                    type="radio"
                    name={radioName}
                    value={category}
                    checked={checked}
                    disabled={isSaving}
                    onChange={() => {
                      setSelectedCategory(category);
                      setJustSaved(false);
                      setErrorMessage(null);
                    }}
                    className="sr-only"
                  />
                  <span
                    aria-hidden="true"
                    className={
                      "flex h-4 w-4 flex-none items-center justify-center rounded-full border " +
                      (checked
                        ? "border-primary bg-primary"
                        : "border-subtle bg-white")
                    }
                  >
                    {checked ? (
                      <span className="h-1.5 w-1.5 rounded-full bg-white" />
                    ) : null}
                  </span>
                  <span>{t(DECISION_CATEGORY_LABEL[category])}</span>
                </label>
              );
            })}
          </div>

          {selectedCategory === null ? (
            <p className="mt-2 mb-0 text-xs leading-[18px] text-muted">
              {t("audit.decision.noneSelected")}
            </p>
          ) : null}

          <label
            htmlFor={textareaId}
            className="mt-3.5 mb-1.5 block text-sm font-semibold text-text"
          >
            {t("audit.decision.justificationLabel")}{" "}
            <span className="font-normal text-muted">
              {t("audit.form.required")}
            </span>
          </label>
          <textarea
            id={textareaId}
            rows={4}
            maxLength={MAX_JUSTIFICATION_LENGTH}
            value={justification}
            disabled={isSaving}
            onChange={(event) => {
              setJustification(event.target.value);
              setJustSaved(false);
              setErrorMessage(null);
            }}
            placeholder={t("audit.decision.justificationPlaceholder")}
            className="box-border h-24 w-full resize-y rounded-lg border border-subtle bg-white px-3 py-2.5 font-sans text-sm leading-[22px] text-text placeholder:text-[#6b7078] disabled:bg-field-disabled"
          />

          <button
            type="submit"
            disabled={!canSubmit}
            className={
              "mt-3 block h-10 w-full rounded-lg border-0 font-sans text-[13px] font-medium " +
              (canSubmit
                ? "cursor-pointer bg-primary text-white hover:brightness-95"
                : "cursor-not-allowed bg-nav-active text-chip-text")
            }
          >
            {submitLabel}
          </button>

          {justSaved && !errorMessage ? (
            <p
              role="status"
              className="mt-2.5 mb-0 flex items-center gap-1.5 text-xs leading-[18px] font-medium text-supported-text"
            >
              <SupportedIcon
                size={14}
                className="flex-none text-supported-icon"
              />
              <span>{t("audit.decision.savedConfirmation")}</span>
            </p>
          ) : null}

          {errorMessage ? (
            <p
              role="alert"
              className="mt-2.5 mb-0 flex items-start gap-1.5 rounded-lg bg-conflict-bg px-3 py-2 text-xs leading-[18px] text-conflict-text"
            >
              <InfoIcon
                size={14}
                className="mt-0.5 flex-none text-conflict-icon"
              />
              <span>{errorMessage}</span>
            </p>
          ) : null}

          {savedDecision && !justSaved ? (
            <p className="mt-2 mb-0 text-xs leading-[18px] text-muted">
              {t("audit.decision.lastSaved", {
                role: savedRoleLabel,
                time: formatAuditTimestamp(savedDecision.updated_at, lang),
              })}
            </p>
          ) : null}

          <p className="mt-2 mb-0 text-xs leading-[18px] text-muted">
            {t("audit.decision.disclaimer")}
          </p>
        </form>
      )}
    </div>
  );
}
