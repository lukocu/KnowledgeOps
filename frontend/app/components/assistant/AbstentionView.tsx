import type { Ref } from "react";

import type { AbstainedResult, AnswerRecord } from "../../api/answers";
import { useT } from "../../i18n/context";
import { Icon, InfoIcon } from "./Icon";
import { PreparationDetails } from "./PreparationDetails";

const ACTION_BUTTON =
  "inline-flex min-h-10 cursor-pointer items-center gap-2.5 self-start rounded-lg border-0 px-3.5 text-sm text-text";

/**
 * Abstencja (1C): neutralny ton, bez czerwieni. Akcje: doprecyzowanie pytania i panel
 * sprawdzonych fragmentów. Pozycji przekazania do audytu nie pokazujemy do S-08.
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
        <svg
          aria-hidden="true"
          width="24"
          height="24"
          viewBox="0 0 16 16"
          className="flex-none"
        >
          <circle
            cx="8"
            cy="8"
            r="6"
            fill="none"
            stroke="#3f434a"
            strokeWidth="1.4"
            strokeDasharray="2.2 1.8"
          />
          <path
            d="M6.4 6.4a1.7 1.7 0 1 1 2.3 1.6c-.5.2-.7.5-.7 1v.3"
            fill="none"
            stroke="#3f434a"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <circle cx="8" cy="11.1" r=".8" fill="#3f434a" />
        </svg>
        <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
          {t("abstain.title")}
        </h1>
      </div>
      <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
        {t("abstain.explain")}
      </p>
      <p className="mt-2.5 mb-0 flex max-w-[680px] items-start gap-2 text-sm leading-[22px] text-[#3d4046]">
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
                ? " bg-[#eef2fc] shadow-[inset_0_0_0_1px_var(--color-primary)]"
                : " bg-white shadow-[inset_0_0_0_1px_var(--color-border)]")
            }
          >
            <Icon>
              <path d="M7 3h7l5 5v13H7z" />
              <path d="M14 3v5h5" />
            </Icon>
            {t("abstain.checked", { n: result.checked_chunks.length })}
          </button>
        </div>
      </div>

      <div className="mt-[18px] max-w-[680px]">
        <PreparationDetails record={record} />
      </div>
    </div>
  );
}
