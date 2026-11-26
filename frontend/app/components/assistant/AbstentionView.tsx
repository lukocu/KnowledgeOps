import type { Ref } from "react";
import { Link } from "react-router";

import type { AbstainedResult, AnswerRecord } from "../../api/answers";
import { useT } from "../../i18n/context";
import { AuditNavIcon, Icon, InfoIcon, InsufficientIcon } from "./Icon";
import { PreparationDetails } from "./PreparationDetails";

const ACTION_BUTTON =
  "inline-flex min-h-10 cursor-pointer items-center gap-2.5 self-start rounded-lg border-0 px-3.5 text-sm text-text no-underline";

/**
 * Abstencja (1C): neutralny ton, bez czerwieni. Akcje: doprecyzowanie pytania,
 * panel sprawdzonych fragmentów oraz drugorzędny link do audytu sprawy (D6).
 */
export function AbstentionView({
  record,
  result,
  checkedOpen,
  checkedButtonRef,
  onRefine,
  onToggleChecked,
}: {
  record: AnswerRecord;
  result: AbstainedResult;
  checkedOpen: boolean;
  checkedButtonRef?: Ref<HTMLButtonElement>;
  onRefine: () => void;
  onToggleChecked: () => void;
}) {
  const t = useT();

  return (
    <div className="mt-7">
      <div className="flex items-center gap-2.5">
        {/* Przerywane kółko ze znakiem zapytania: brak dowodu, nie błąd. */}
        <InsufficientIcon size={24} className="flex-none text-icon" />
        <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
          {t("abstain.title")}
        </h1>
      </div>
      <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
        {t("abstain.explain")}
      </p>
      <p className="mt-2.5 mb-0 flex max-w-[680px] items-start gap-2 text-sm leading-[22px] text-secondary">
        <span className="mt-[3px] flex-none text-muted">
          <InfoIcon />
        </span>
        <span>{t("abstain.note")}</span>
      </p>

      <div className="mt-5">
        <h2 className="m-0 mb-2 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
          {t("abstain.actions")}
        </h2>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={onRefine}
            className={
              ACTION_BUTTON +
              " bg-white shadow-[inset_0_0_0_1px_var(--color-border)]"
            }
          >
            <Icon>
              <path d="M4 20h4L19 9l-4-4L4 16z" />
            </Icon>
            {t("abstain.refine")}
          </button>
          <button
            ref={checkedButtonRef}
            type="button"
            aria-pressed={checkedOpen}
            onClick={onToggleChecked}
            className={
              ACTION_BUTTON +
              (checkedOpen
                ? " bg-claim-selected shadow-[inset_0_0_0_1px_var(--color-primary)]"
                : " bg-white shadow-[inset_0_0_0_1px_var(--color-border)]")
            }
          >
            <Icon>
              <path d="M7 3h7l5 5v13H7z" />
              <path d="M14 3v5h5" />
            </Icon>
            {t("abstain.checked", { n: result.checked_chunks.length })}
          </button>
          <Link
            to="/audyt"
            className={
              ACTION_BUTTON +
              " bg-transparent px-1 text-muted hover:text-text hover:underline"
            }
          >
            <AuditNavIcon size={16} />
            {t("abstain.submitAudit")}
          </Link>
        </div>
      </div>

      <div className="mt-[18px] max-w-[680px]">
        <PreparationDetails record={record} />
      </div>
    </div>
  );
}
