import { useT } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/pl";
import type { Step, StepId, StepStatus } from "../../lib/stages";
import { CheckIcon } from "./Icon";

const STEP_LABELS: Record<StepId, TranslationKey> = {
  search: "progress.search",
  check: "progress.check",
  compose: "progress.compose",
};

const STATUS_WORDS: Record<StepStatus, TranslationKey> = {
  pending: "progress.pending",
  active: "progress.active",
  done: "progress.done",
};

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === "done") return <CheckIcon size={18} stroke="#1a6b36" />;
  if (status === "active") {
    return (
      <svg
        aria-hidden="true"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#2f5fc4"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="flex-none animate-spin"
      >
        <path d="M12 3a9 9 0 1 0 9 9" />
      </svg>
    );
  }
  return (
    <span
      aria-hidden="true"
      className="inline-block h-[18px] w-[18px] flex-none rounded-full border-[1.5px] border-subtle"
    />
  );
}

/** Karta postępu (S1P): stan kroków wynika wyłącznie z odebranych zdarzeń `stage`. */
export function ProgressCard({ steps }: { steps: Step[] }) {
  const t = useT();

  return (
    <div role="status" className="mt-[22px]">
      <section className="max-w-[640px] rounded-xl bg-surface px-5 py-[18px]">
        <div className="mb-3.5 text-base font-semibold">
          {t("progress.title")}
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
              <StatusIcon status={status} />
              <span className="flex-1">{t(STEP_LABELS[id])}</span>
              <span className="text-[13px] font-normal text-muted">
                {t(STATUS_WORDS[status])}
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-4 mb-0 text-[13px] leading-5 text-muted">
          {t("progress.hint")}
        </p>
      </section>
    </div>
  );
}
