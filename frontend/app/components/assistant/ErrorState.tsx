import { Link } from "react-router";

import type { ErrorEvent } from "../../api/answers";
import { useT } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/pl";
import { InfoIcon } from "./Icon";

const MESSAGES: Record<ErrorEvent["code"], TranslationKey> = {
  model_not_configured: "errorState.modelNotConfigured",
  model_unavailable: "errorState.modelUnavailable",
  database_unavailable: "errorState.databaseUnavailable",
  internal: "errorState.internal",
};

const PRIMARY_BUTTON =
  "inline-flex h-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-primary px-4 text-sm font-medium whitespace-nowrap text-white no-underline hover:brightness-95";

/** Neutralny stan błędu w tonie 1C: ikona i słowo, bez czerwieni. */
export function ErrorState({
  code,
  onRetry,
}: {
  code: ErrorEvent["code"];
  onRetry: () => void;
}) {
  const t = useT();

  return (
    <section role="alert" className="mt-7">
      <div className="flex items-center gap-2.5">
        <InfoIcon size={24} stroke="#3f434a" />
        <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
          {t("errorState.title")}
        </h1>
      </div>
      <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
        {t(MESSAGES[code])}
      </p>
      <p className="mt-2.5 mb-0 flex max-w-[680px] items-start gap-2 text-sm leading-[22px] text-[#3d4046]">
        <span className="mt-[3px] flex-none text-muted">
          <InfoIcon />
        </span>
        <span>{t("errorState.note")}</span>
      </p>
      <div className="mt-5">
        <button type="button" onClick={onRetry} className={PRIMARY_BUTTON}>
          {t("errorState.retry")}
        </button>
      </div>
    </section>
  );
}

/** 404 dla `/odpowiedz/:id`: odpowiedź należy do innej sesji albo nie istnieje. */
export function AnswerNotFound() {
  const t = useT();

  return (
    <section className="mt-7">
      <div className="flex items-center gap-2.5">
        <InfoIcon size={24} stroke="#3f434a" />
        <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
          {t("errorState.notFoundTitle")}
        </h1>
      </div>
      <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
        {t("errorState.notFoundBody")}
      </p>
      <div className="mt-5">
        <Link to="/" className={PRIMARY_BUTTON}>
          {t("errorState.newQuestion")}
        </Link>
      </div>
    </section>
  );
}
