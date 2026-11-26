import type { AuditDetailResponse } from "../../api/audits";
import { useLanguage, useT } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/pl";
import { deriveAuditSteps, type AuditProgressStepId } from "../../lib/audit";
import { pluralForm } from "../../lib/plural";
import type { StepStatus } from "../../lib/stages";
import { StepStatusIcon } from "../assistant/Icon";

const STATUS_WORDS: Record<StepStatus, TranslationKey> = {
  pending: "progress.pending",
  active: "progress.active",
  done: "progress.done",
};

/** Prawy panel postępu dla ekranu 2P (`queued` / `running`). */
export function AuditProgressAside({ audit }: { audit: AuditDetailResponse }) {
  const t = useT();
  const { lang } = useLanguage();
  const steps = deriveAuditSteps(audit.stage, audit.status);

  function stepLabel(id: AuditProgressStepId, status: StepStatus): string {
    if (id === "extract") {
      if (status === "done" && audit.claims_total > 0) {
        return t(
          `audit.progress.stepExtractDone${pluralForm(lang, audit.claims_total)}`,
          { n: audit.claims_total },
        );
      }
      return t("audit.progress.stepExtract");
    }
    if (id === "retrieve") {
      if (status === "active" && audit.claims_total > 0) {
        const current = Math.min(audit.claims_done + 1, audit.claims_total);
        return t("audit.progress.stepRetrieveProgress", {
          current,
          total: audit.claims_total,
        });
      }
      if (status === "done") {
        return t("audit.progress.stepRetrieveDone");
      }
      return t("audit.progress.stepRetrieve");
    }
    return t("audit.progress.stepVerdict");
  }

  return (
    <aside
      role="status"
      aria-live="polite"
      className="w-full flex-none border-t border-border-soft bg-aside-soft p-6 lg:w-[400px] lg:border-t-0 lg:border-l"
    >
      <div className="mb-3.5 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
        {audit.case_ref
          ? t("audit.progress.titleWithRef", { ref: audit.case_ref })
          : t("audit.progress.title")}
      </div>
      <ol className="m-0 flex list-none flex-col gap-3.5 p-0">
        {steps.map(({ id, status }) => (
          <li
            key={id}
            aria-current={status === "active" ? "step" : undefined}
            className={
              "flex items-center gap-3 text-[15px] " +
              (status === "active" ? "font-semibold" : "font-normal")
            }
          >
            <StepStatusIcon status={status} />
            <span className="min-w-0 flex-1">{stepLabel(id, status)}</span>
            <span className="flex-none text-[13px] font-normal text-muted">
              {t(STATUS_WORDS[status])}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-4 mb-0 text-[13px] leading-5 text-muted">
        {t("audit.progress.backgroundHint")}
      </p>
    </aside>
  );
}
