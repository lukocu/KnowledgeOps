import type { AuditHistoryEventResponse } from "../../api/audits";
import { useLanguage, useT } from "../../i18n/context";
import {
  claimTag,
  DECISION_CATEGORY_LABEL,
  formatAuditTimestamp,
  HISTORY_EVENT_LABEL,
  NOTE_VERDICT_LABEL,
} from "../../lib/audit";
import { pluralForm } from "../../lib/plural";
import { ChevronIcon, PersonIcon, SystemIcon } from "../assistant/Icon";

/**
 * Zwinięta sekcja `<details>` „Historia” (S3/S3N): pokazuje wyłącznie
 * rzeczywiste zdarzenia z `audit.history` z rozróżnieniem systemu i człowieka.
 */
export function AuditHistoryDetails({
  history,
}: {
  history: readonly AuditHistoryEventResponse[];
}) {
  const t = useT();
  const { lang } = useLanguage();

  const count = history.length;
  const countLabel = t(`audit.history.count${pluralForm(lang, count)}`, {
    n: count,
  });
  const lastEvent = count > 0 ? history[count - 1] : null;

  function formatShortEventLabel(event: AuditHistoryEventResponse): string {
    const base = t(HISTORY_EVENT_LABEL[event.event_type]);
    if (event.claim_index !== null && event.claim_index !== undefined) {
      return `${base} (${claimTag(event.claim_index)})`;
    }
    return base;
  }

  function formatActorLabel(event: AuditHistoryEventResponse): string {
    if (event.actor_type === "system") {
      return t("audit.history.actorSystem");
    }
    return event.role_label === "consultant"
      ? t("header.roleConsultant")
      : t("header.roleEditor");
  }

  const summaryRight = lastEvent
    ? `${countLabel} · ${t("audit.history.last", {
        label: formatShortEventLabel(lastEvent).toLowerCase(),
      })}`
    : countLabel;

  return (
    <details className="group border-t border-border-soft">
      <summary className="flex min-h-6 cursor-pointer list-none items-center gap-2 px-0.5 py-2.5 text-sm text-text [&::-webkit-details-marker]:hidden">
        <span className="inline-flex text-muted transition-transform group-open:rotate-90">
          <ChevronIcon direction="right" size={16} />
        </span>
        <span className="flex-1">{t("audit.history.title")}</span>
        <span className="text-right text-xs text-muted">{summaryRight}</span>
      </summary>

      {count === 0 ? (
        <p className="m-0 pr-0.5 pb-3 pl-[26px] text-[13px] leading-5 text-muted">
          {t("audit.history.empty")}
        </p>
      ) : (
        <ol className="m-0 list-none space-y-2 pr-0.5 pb-3 pl-[26px]">
          {history.map((event) => {
            const isHuman = event.actor_type === "human";
            const actorLabel = formatActorLabel(event);
            const eventTitle = t(HISTORY_EVENT_LABEL[event.event_type]);
            const tag =
              event.claim_index !== null && event.claim_index !== undefined
                ? claimTag(event.claim_index)
                : null;
            const decisionLabel = event.decision
              ? t(DECISION_CATEGORY_LABEL[event.decision])
              : null;
            const verdictLabel = event.note_verdict
              ? t(NOTE_VERDICT_LABEL[event.note_verdict])
              : null;

            return (
              <li
                key={event.event_id}
                className="flex items-start gap-2 text-[13px] leading-5"
              >
                {isHuman ? (
                  <PersonIcon
                    size={14}
                    className="mt-0.5 flex-none text-text"
                  />
                ) : (
                  <SystemIcon
                    size={14}
                    className="mt-0.5 flex-none text-muted"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                    <span
                      className={
                        isHuman
                          ? "font-semibold text-text"
                          : "font-medium text-muted"
                      }
                    >
                      {actorLabel}
                    </span>
                    <span aria-hidden="true" className="text-muted">
                      ·
                    </span>
                    <span className="text-text">
                      {eventTitle}
                      {tag ? ` (${tag})` : ""}
                      {decisionLabel ? ` — ${decisionLabel}` : ""}
                      {!decisionLabel && verdictLabel
                        ? ` — ${verdictLabel}`
                        : ""}
                    </span>
                  </div>
                </div>
                <time
                  dateTime={event.created_at}
                  className="flex-none text-xs text-muted tabular-nums"
                >
                  {formatAuditTimestamp(event.created_at, lang)}
                </time>
              </li>
            );
          })}
        </ol>
      )}
    </details>
  );
}
