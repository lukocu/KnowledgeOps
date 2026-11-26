import type { FormEvent, ReactNode } from "react";

import { useT } from "../../i18n/context";
import { MAX_AUDIT_TEXT_LENGTH, MAX_CASE_REF_LENGTH } from "../../lib/audit";
import { InfoIcon } from "../assistant/Icon";

export type AuditFormValues = {
  caseRef: string;
  caseDescription: string;
  resolutionNote: string;
};

/** Prawy panel informacyjny ekranu 2: „Co się stanie po uruchomieniu”. */
export function AuditHowItWorksAside() {
  const t = useT();
  const steps = [
    {
      n: 1,
      title: t("audit.aside.step1Title"),
      desc: t("audit.aside.step1Desc"),
    },
    {
      n: 2,
      title: t("audit.aside.step2Title"),
      desc: t("audit.aside.step2Desc"),
    },
    {
      n: 3,
      title: t("audit.aside.step3Title"),
      desc: t("audit.aside.step3Desc"),
    },
    {
      n: 4,
      title: t("audit.aside.step4Title"),
      desc: t("audit.aside.step4Desc"),
    },
  ];

  return (
    <aside className="w-full flex-none border-t border-border-soft bg-aside-soft p-6 lg:w-[400px] lg:border-t-0 lg:border-l">
      <div className="mb-3.5 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
        {t("audit.aside.title")}
      </div>
      <ol className="m-0 flex list-none flex-col gap-4 p-0">
        {steps.map((step) => (
          <li key={step.n} className="flex gap-3">
            <span
              aria-hidden="true"
              className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full bg-white text-xs font-semibold text-muted"
            >
              {step.n}
            </span>
            <div className="min-w-0">
              <div className="text-[15px] font-semibold">{step.title}</div>
              <div className="text-[13px] leading-5 text-muted">
                {step.desc}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </aside>
  );
}

/**
 * Formularz przekazania sprawy do audytu (ekran 2 oraz wariant zablokowany 2P).
 * Poniżej 1024 px (`lg`) układa panel boczny pod formularzem bez przewijania w poziomie.
 */
export function AuditFormView({
  values,
  mode,
  errorMessage,
  onChange,
  onSubmit,
  onClear,
  aside,
}: {
  values: AuditFormValues;
  mode: "editable" | "submitting" | "running";
  errorMessage?: string | null;
  onChange?: (patch: Partial<AuditFormValues>) => void;
  onSubmit?: () => void;
  onClear?: () => void;
  aside: ReactNode;
}) {
  const t = useT();
  const disabled = mode !== "editable";
  const fieldBg = mode === "running" ? "bg-field-disabled" : "bg-surface";

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!disabled) onSubmit?.();
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="min-w-0 flex-1 overflow-y-auto px-4 py-6 md:px-6 lg:px-10 lg:py-8">
        <div className="max-w-[780px]">
          <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
            {t("audit.form.title")}
          </h1>
          <p className="mt-2 mb-0 text-sm leading-[22px] text-muted">
            {t("audit.form.intro")}
          </p>

          <div className="mt-3.5 flex items-start gap-2.5 rounded-lg bg-surface px-3.5 py-2.5 text-sm leading-[22px]">
            <span className="mt-[3px] flex-none text-muted">
              <InfoIcon size={16} />
            </span>
            <span>{t("audit.form.notice")}</span>
          </div>

          {errorMessage ? (
            <div
              role="alert"
              className="mt-4 flex items-start gap-2.5 rounded-lg border border-border bg-surface-alt px-3.5 py-2.5 text-sm leading-[22px] text-text"
            >
              <span className="mt-[3px] flex-none text-icon">
                <InfoIcon size={16} />
              </span>
              <span>{errorMessage}</span>
            </div>
          ) : null}

          <form onSubmit={handleSubmit} noValidate>
            <div className="mt-[18px] max-w-[300px]">
              <label
                htmlFor="audit-case-ref"
                className="mb-1.5 block text-sm font-semibold"
              >
                {t("audit.form.caseRefLabel")}{" "}
                <span className="font-normal text-muted">
                  {t("audit.form.caseRefOptional")}
                </span>
              </label>
              <input
                id="audit-case-ref"
                type="text"
                value={values.caseRef}
                disabled={disabled}
                maxLength={MAX_CASE_REF_LENGTH}
                placeholder={t("audit.form.caseRefPlaceholder")}
                onChange={(event) =>
                  onChange?.({ caseRef: event.target.value })
                }
                className={
                  "box-border h-10 w-full rounded-lg border-0 px-3.5 py-2.5 font-mono text-[13px] leading-[22px] text-text placeholder:text-[#6b7078] " +
                  fieldBg
                }
              />
            </div>

            <div className="mt-4">
              <label
                htmlFor="audit-case-description"
                className="mb-1.5 block text-sm font-semibold"
              >
                {t("audit.form.descriptionLabel")}{" "}
                <span className="font-normal text-muted">
                  {t("audit.form.required")}
                </span>
              </label>
              <textarea
                id="audit-case-description"
                rows={4}
                required
                value={values.caseDescription}
                disabled={disabled}
                maxLength={MAX_AUDIT_TEXT_LENGTH}
                placeholder={t("audit.form.descriptionPlaceholder")}
                onChange={(event) =>
                  onChange?.({ caseDescription: event.target.value })
                }
                className={
                  "box-border min-h-[104px] w-full resize-y rounded-lg border-0 px-3.5 py-2.5 font-sans text-sm leading-[22px] text-text placeholder:text-[#6b7078] " +
                  fieldBg
                }
              />
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs leading-[18px] text-muted">
                <span>{t("audit.form.descriptionHint")}</span>
                <span className="font-mono">
                  {values.caseDescription.length} / {MAX_AUDIT_TEXT_LENGTH}
                </span>
              </div>
            </div>

            <div className="mt-3.5">
              <label
                htmlFor="audit-resolution-note"
                className="mb-1.5 block text-sm font-semibold"
              >
                {t("audit.form.noteLabel")}{" "}
                <span className="font-normal text-muted">
                  {t("audit.form.required")}
                </span>
              </label>
              <textarea
                id="audit-resolution-note"
                rows={4}
                required
                value={values.resolutionNote}
                disabled={disabled}
                maxLength={MAX_AUDIT_TEXT_LENGTH}
                placeholder={t("audit.form.notePlaceholder")}
                onChange={(event) =>
                  onChange?.({ resolutionNote: event.target.value })
                }
                className={
                  "box-border min-h-[104px] w-full resize-y rounded-lg border-0 px-3.5 py-2.5 font-sans text-sm leading-[22px] text-text placeholder:text-[#6b7078] " +
                  fieldBg
                }
              />
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs leading-[18px] text-muted">
                <span>{t("audit.form.noteHint")}</span>
                <span className="font-mono">
                  {values.resolutionNote.length} / {MAX_AUDIT_TEXT_LENGTH}
                </span>
              </div>
            </div>

            <div className="mt-[18px] flex flex-wrap items-center gap-3">
              {mode === "running" ? (
                <button
                  type="button"
                  disabled
                  className="inline-flex h-9 flex-none items-center justify-center rounded-lg border-0 bg-surface px-4 text-sm font-medium whitespace-nowrap text-chip-text"
                >
                  {t("audit.form.running")}
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={disabled}
                  className="inline-flex h-9 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-primary px-4 text-sm font-medium whitespace-nowrap text-white hover:brightness-95 disabled:cursor-wait disabled:opacity-70"
                >
                  {mode === "submitting"
                    ? t("audit.form.submitting")
                    : t("audit.form.submit")}
                </button>
              )}
              <button
                type="button"
                disabled={disabled}
                onClick={onClear}
                className="inline-flex h-9 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-surface px-3 text-[13px] font-medium whitespace-nowrap text-text hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-55"
              >
                {t("audit.form.clear")}
              </button>
              <span className="text-[13px] text-muted">
                {t("audit.form.doesNotChangeDocs")}
              </span>
            </div>
          </form>
        </div>
      </div>

      {aside}
    </div>
  );
}
