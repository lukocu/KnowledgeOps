import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import {
  fetchAudits,
  type AuditListItemResponse,
  type AuditListResponse,
  type AuditSourceFilter,
  type DecisionStatus,
  type NoteVerdict,
} from "../../api/audits";
import { useLanguage, useT } from "../../i18n/context";
import {
  countAwaitingDecision,
  formatClaimBreakdown,
  formatCompactTimestamp,
  formatSummaryLine,
  hasActiveSearchOrStatusFilters,
} from "../../lib/audit";
import { pluralForm } from "../../lib/plural";
import { ChevronIcon, InfoIcon, SearchIcon } from "../assistant/Icon";
import { DecisionStatusPill, NoteVerdictPill } from "./AuditBadges";

const POLL_INTERVAL_MS = 3000;
const SEARCH_DEBOUNCE_MS = 250;

const DECISION_OPTIONS: readonly DecisionStatus[] = [
  "pending",
  "in_progress",
  "saved",
  "not_applicable",
];

const VERDICT_OPTIONS: readonly NoteVerdict[] = [
  "contradiction",
  "partial",
  "full",
  "insufficient",
];

const SOURCE_OPTIONS: readonly AuditSourceFilter[] = ["all", "demo", "session"];

type ListLoadState =
  | { status: "loading" }
  | { status: "ready"; data: AuditListResponse }
  | { status: "error" };

function parseDecisionStatus(value: string | null): DecisionStatus | null {
  if (value && DECISION_OPTIONS.includes(value as DecisionStatus)) {
    return value as DecisionStatus;
  }
  return null;
}

function parseNoteVerdict(value: string | null): NoteVerdict | null {
  if (value && VERDICT_OPTIONS.includes(value as NoteVerdict)) {
    return value as NoteVerdict;
  }
  return null;
}

function parseSourceFilter(value: string | null): AuditSourceFilter {
  if (value && SOURCE_OPTIONS.includes(value as AuditSourceFilter)) {
    return value as AuditSourceFilter;
  }
  return "all";
}

function displayCaseRef(item: AuditListItemResponse): string {
  return item.case_ref?.trim() || item.audit_id.slice(0, 8);
}

function isRowEmphasized(item: AuditListItemResponse): boolean {
  return (
    item.status === "completed" &&
    (item.decision_status === "pending" ||
      item.decision_status === "in_progress")
  );
}

/**
 * Ekran 5 („Analizy i decyzje”): lista przykładów demo i analiz z bieżącej sesji,
 * filtry zsynchronizowane z URL, oba stany puste, polling dla analiz w toku
 * oraz responsywny widok kartowy poniżej 768 px (390 px bez przewijania w poziomie).
 */
export function AnalysesListView() {
  const t = useT();
  const { lang } = useLanguage();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const urlQ = searchParams.get("q") ?? "";
  const decisionStatus = parseDecisionStatus(
    searchParams.get("decision_status"),
  );
  const noteVerdict = parseNoteVerdict(searchParams.get("note_verdict"));
  const source = parseSourceFilter(searchParams.get("source"));

  const [searchInput, setSearchInput] = useState(urlQ);
  const [prevUrlQ, setPrevUrlQ] = useState(urlQ);
  if (urlQ !== prevUrlQ) {
    setPrevUrlQ(urlQ);
    if (searchInput.trim() !== urlQ) {
      setSearchInput(urlQ);
    }
  }

  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<ListLoadState>({ status: "loading" });

  useEffect(() => {
    const trimmedInput = searchInput.trim();
    const trimmedUrl = urlQ.trim();
    if (trimmedInput === trimmedUrl) return;
    const timer = window.setTimeout(() => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (trimmedInput) {
            next.set("q", trimmedInput);
          } else {
            next.delete("q");
          }
          return next;
        },
        { replace: true },
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput, urlQ, setSearchParams]);

  useEffect(() => {
    let active = true;
    let timerId: number | undefined;
    let controller = new AbortController();

    async function load() {
      controller = new AbortController();
      try {
        const data = await fetchAudits(
          {
            q: urlQ || undefined,
            decision_status: decisionStatus,
            note_verdict: noteVerdict,
            source,
          },
          controller.signal,
        );
        if (!active) return;
        setState({ status: "ready", data });
        const hasInFlight = data.items.some(
          (item) => item.status === "queued" || item.status === "running",
        );
        if (hasInFlight) {
          timerId = window.setTimeout(() => {
            void load();
          }, POLL_INTERVAL_MS);
        }
      } catch {
        if (!active || controller.signal.aborted) return;
        setState({ status: "error" });
      }
    }

    void load();

    return () => {
      active = false;
      if (timerId !== undefined) window.clearTimeout(timerId);
      controller.abort();
    };
  }, [urlQ, decisionStatus, noteVerdict, source, attempt]);

  function updateParam(key: string, value: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  }

  function clearFilters() {
    setSearchInput("");
    setSearchParams({}, { replace: true });
  }

  const activeFilters = {
    q: urlQ,
    decision_status: decisionStatus,
    note_verdict: noteVerdict,
    source,
  };
  const hasSearchOrStatus = hasActiveSearchOrStatusFilters(activeFilters);

  const summary = state.status === "ready" ? state.data.summary : null;
  const items = state.status === "ready" ? state.data.items : [];
  const waitingCount = summary ? countAwaitingDecision(summary) : 0;

  const showSessionEmptyBanner =
    state.status === "ready" &&
    items.length > 0 &&
    summary !== null &&
    summary.session_count === 0 &&
    source !== "demo" &&
    !hasSearchOrStatus;

  const showSessionEmptyFull =
    state.status === "ready" &&
    items.length === 0 &&
    summary !== null &&
    summary.session_count === 0 &&
    !hasSearchOrStatus &&
    (source === "session" || (source === "all" && summary.demo_count === 0));

  const showFilterEmptyFull =
    state.status === "ready" && items.length === 0 && !showSessionEmptyFull;

  return (
    <div className="flex min-h-0 flex-1 flex-col px-4 py-5 md:px-6 lg:px-8">
      {/* Nagłówek */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
          {t("analyses.title")}
        </h1>
        <span
          title={t("analyses.demoChipTooltip")}
          className="inline-flex cursor-help items-center gap-1.5 rounded-md bg-chip px-2 py-px text-xs leading-5 font-semibold tracking-[.04em] whitespace-nowrap text-chip-text"
        >
          {t("analyses.demoChip")}
          <InfoIcon size={13} />
        </span>
      </div>
      <p className="mt-1 mb-0 text-sm leading-[22px] text-muted">
        {t("analyses.subtitle")}
      </p>

      {/* Baner akcji (analizy czekające na decyzję) */}
      {summary?.next_pending_audit_id ? (
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[10px] bg-surface px-4 py-2.5">
          <span
            aria-hidden="true"
            className="h-2 w-2 flex-none rounded-full bg-primary"
          />
          <span className="text-sm leading-[22px] font-semibold text-text">
            {t(`analyses.banner.waiting${pluralForm(lang, waitingCount)}`, {
              n: waitingCount,
            })}
          </span>
          <Link
            to={`/audyt/${summary.next_pending_audit_id}`}
            className="ml-auto inline-flex h-8 flex-none items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium whitespace-nowrap text-white no-underline hover:brightness-95"
          >
            {summary.next_pending_case_ref
              ? t("analyses.banner.startWithRef", {
                  ref: summary.next_pending_case_ref,
                })
              : t("analyses.banner.startDefault")}
          </Link>
        </div>
      ) : null}

      {/* Pasek filtrów + podsumowanie */}
      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <div className="relative w-full sm:w-[280px] lg:w-[300px]">
          <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted">
            <SearchIcon size={16} />
          </span>
          <input
            type="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            aria-label={t("analyses.filter.searchLabel")}
            placeholder={t("analyses.filter.searchPlaceholder")}
            className="box-border h-[34px] w-full rounded-lg border-0 bg-surface pr-3 pl-8.5 font-sans text-[13px] text-text placeholder:text-muted"
          />
        </div>

        <label className="inline-flex h-[34px] max-w-full items-center gap-1.5 rounded-lg bg-surface px-3 text-[13px]">
          <span className="flex-none text-muted">
            {t("analyses.filter.decisionLabel")}
          </span>
          <select
            aria-label={t("analyses.filter.decisionLabel")}
            value={decisionStatus ?? ""}
            onChange={(event) =>
              updateParam("decision_status", event.target.value || null)
            }
            className="min-w-0 cursor-pointer border-0 bg-transparent font-sans text-[13px] font-semibold text-text outline-0"
          >
            <option value="">{t("analyses.filter.all")}</option>
            <option value="pending">{t("analyses.decision.pending")}</option>
            <option value="in_progress">
              {t("analyses.decision.in_progress")}
            </option>
            <option value="saved">{t("analyses.decision.saved")}</option>
            <option value="not_applicable">
              {t("analyses.decision.not_applicable")}
            </option>
          </select>
        </label>

        <label className="inline-flex h-[34px] max-w-full items-center gap-1.5 rounded-lg bg-surface px-3 text-[13px]">
          <span className="flex-none text-muted">
            {t("analyses.filter.verdictLabel")}
          </span>
          <select
            aria-label={t("analyses.filter.verdictLabel")}
            value={noteVerdict ?? ""}
            onChange={(event) =>
              updateParam("note_verdict", event.target.value || null)
            }
            className="min-w-0 cursor-pointer border-0 bg-transparent font-sans text-[13px] font-semibold text-text outline-0"
          >
            <option value="">{t("analyses.filter.all")}</option>
            <option value="contradiction">
              {t("audit.verdict.note.contradiction")}
            </option>
            <option value="partial">{t("audit.verdict.note.partial")}</option>
            <option value="full">{t("audit.verdict.note.full")}</option>
            <option value="insufficient">
              {t("audit.verdict.note.insufficient")}
            </option>
          </select>
        </label>

        <label className="inline-flex h-[34px] max-w-full items-center gap-1.5 rounded-lg bg-surface px-3 text-[13px]">
          <span className="flex-none text-muted">
            {t("analyses.filter.sourceLabel")}
          </span>
          <select
            aria-label={t("analyses.filter.sourceLabel")}
            value={source}
            onChange={(event) => {
              const nextSource = event.target.value;
              updateParam("source", nextSource === "all" ? null : nextSource);
            }}
            className="min-w-0 cursor-pointer border-0 bg-transparent font-sans text-[13px] font-semibold text-text outline-0"
          >
            <option value="all">{t("analyses.filter.all")}</option>
            <option value="demo">{t("analyses.filter.sourceDemo")}</option>
            <option value="session">
              {t("analyses.filter.sourceSession")}
            </option>
          </select>
        </label>

        {summary ? (
          <span className="w-full text-[13px] text-muted xl:ml-auto xl:w-auto">
            {formatSummaryLine(summary, t, lang)}
          </span>
        ) : null}
      </div>

      {/* Stan ładowania */}
      {state.status === "loading" ? (
        <p role="status" className="mt-6 mb-0 text-[15px] leading-6 text-muted">
          {t("analyses.loading")}
        </p>
      ) : null}

      {/* Stan błędu */}
      {state.status === "error" ? (
        <section
          role="alert"
          className="mt-4 rounded-[10px] p-4 shadow-[inset_0_0_0_1px_var(--color-border-soft)]"
        >
          <div className="flex items-center gap-2">
            <InfoIcon size={18} className="flex-none text-icon" />
            <h2 className="m-0 text-base leading-6 font-semibold">
              {t("analyses.errorTitle")}
            </h2>
          </div>
          <p className="mt-1.5 mb-0 text-sm leading-[22px] text-muted">
            {t("errorState.internal")}
          </p>
          <div className="mt-3">
            <button
              type="button"
              onClick={() => {
                setState({ status: "loading" });
                setAttempt((value) => value + 1);
              }}
              className="inline-flex h-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-primary px-4 font-sans text-sm font-medium whitespace-nowrap text-white hover:brightness-95"
            >
              {t("errorState.retry")}
            </button>
          </div>
        </section>
      ) : null}

      {/* Pasek stanu pustego sesji (gdy widać tylko przykłady demo) */}
      {showSessionEmptyBanner ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-[10px] px-4 py-3 shadow-[inset_0_0_0_1px_var(--color-border-soft)]">
          <div className="min-w-0">
            <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
              {t("analyses.empty.sessionTitle")}
            </div>
            <p className="mt-0.5 mb-0 text-sm leading-[22px] text-text">
              {t("analyses.empty.sessionBody")}
            </p>
          </div>
          <Link
            to="/audyt"
            className="inline-flex h-8 flex-none items-center justify-center rounded-lg bg-surface px-3 text-[13px] font-medium whitespace-nowrap text-primary no-underline hover:underline"
          >
            {t("analyses.empty.sessionCta")}
          </Link>
        </div>
      ) : null}

      {/* Pełny stan pusty sesji */}
      {showSessionEmptyFull ? (
        <section className="mt-4 rounded-[10px] p-5 shadow-[inset_0_0_0_1px_var(--color-border-soft)]">
          <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
            {t("analyses.empty.sessionTitle")}
          </div>
          <p className="mt-1 mb-0 text-sm leading-[22px] text-text">
            {t("analyses.empty.sessionBody")}
          </p>
          <div className="mt-3">
            <Link
              to="/audyt"
              className="inline-flex h-9 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium whitespace-nowrap text-white no-underline hover:brightness-95"
            >
              {t("analyses.empty.sessionCta")}
            </Link>
          </div>
        </section>
      ) : null}

      {/* Stan pusty filtrów */}
      {showFilterEmptyFull ? (
        <section className="mt-4 rounded-[10px] p-5 shadow-[inset_0_0_0_1px_var(--color-border-soft)]">
          <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
            {t("analyses.empty.filterTitle")}
          </div>
          <p className="mt-1 mb-0 text-sm leading-[22px] text-text">
            {t("analyses.empty.filterBody")}
          </p>
          <div className="mt-3">
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex h-8 cursor-pointer items-center justify-center rounded-lg border-0 bg-surface px-3 font-sans text-[13px] font-medium whitespace-nowrap text-primary hover:underline"
            >
              {t("analyses.empty.clearFilters")}
            </button>
          </div>
        </section>
      ) : null}

      {/* Tabela desktop (od 768 px) */}
      {state.status === "ready" && items.length > 0 ? (
        <>
          <div className="mt-3 hidden md:block">
            <table className="w-full table-fixed border-collapse">
              <thead>
                <tr>
                  <th
                    scope="col"
                    className="w-[132px] border-b border-border-soft px-3 py-2 text-left text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase"
                  >
                    {t("analyses.table.colCase")}
                  </th>
                  <th
                    scope="col"
                    className="w-auto border-b border-border-soft px-3 py-2 text-left text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase"
                  >
                    {t("analyses.table.colProblem")}
                  </th>
                  <th
                    scope="col"
                    className="w-[240px] border-b border-border-soft px-3 py-2 text-left text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase lg:w-[280px]"
                  >
                    {t("analyses.table.colVerdict")}
                  </th>
                  <th
                    scope="col"
                    className="w-[185px] border-b border-border-soft px-3 py-2 text-left text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase lg:w-[210px]"
                  >
                    {t("analyses.table.colDecision")}
                  </th>
                  <th
                    scope="col"
                    className="w-[120px] border-b border-border-soft px-3 py-2 text-left text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase lg:w-[130px]"
                  >
                    {t("analyses.table.colUpdated")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const emphasized = isRowEmphasized(item);
                  const breakdown =
                    item.status === "completed"
                      ? formatClaimBreakdown(item, t, lang)
                      : "";
                  const caseLabel = displayCaseRef(item);
                  const targetUrl = `/audyt/${item.audit_id}`;
                  return (
                    <tr
                      key={item.audit_id}
                      onClick={(event) => {
                        const target = event.target as HTMLElement | null;
                        if (target?.closest("a,button")) return;
                        if (window.getSelection()?.toString()) return;
                        void navigate(targetUrl);
                      }}
                      className="cursor-pointer bg-white transition-colors hover:bg-row-hover"
                    >
                      <td className="border-b border-border-soft p-3 align-top">
                        <div className="flex flex-col items-start gap-1">
                          <Link
                            to={targetUrl}
                            className={
                              "font-mono text-[13px] leading-5 [overflow-wrap:anywhere] text-text no-underline hover:underline " +
                              (emphasized ? "font-semibold" : "font-normal")
                            }
                          >
                            {caseLabel}
                          </Link>
                          {item.is_demo ? (
                            <span className="inline-block rounded bg-chip px-1.5 py-px font-sans text-[11px] leading-4 font-semibold tracking-[.03em] text-chip-text">
                              {t("analyses.row.demoBadge")}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td
                        className={
                          "border-b border-border-soft p-3 align-top text-sm leading-5 " +
                          (emphasized ? "font-semibold" : "font-normal")
                        }
                      >
                        <div className="line-clamp-2 [overflow-wrap:anywhere]">
                          {item.problem_summary}
                        </div>
                      </td>
                      <td className="border-b border-border-soft p-3 align-top">
                        {item.status === "completed" && item.note_verdict ? (
                          <>
                            <NoteVerdictPill verdict={item.note_verdict} />
                            {breakdown ? (
                              <div className="mt-1 text-xs leading-[18px] text-muted">
                                {breakdown}
                              </div>
                            ) : null}
                          </>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="border-b border-border-soft p-3 align-top">
                        <DecisionStatusPill
                          variant="inline"
                          status={item.decision_status}
                          auditStatus={item.status}
                          decisionsCount={item.decisions_count}
                          claimsTotal={item.claims_total}
                        />
                        {item.status === "completed" &&
                        item.claims_total > 0 ? (
                          <div className="mt-0.5 text-xs leading-[18px] text-muted">
                            {t("analyses.row.claimsResolved", {
                              done: item.decisions_count,
                              total: item.claims_total,
                            })}
                          </div>
                        ) : null}
                      </td>
                      <td className="border-b border-border-soft p-3 align-top text-[13px] whitespace-nowrap text-muted">
                        <span className="inline-flex items-center gap-1.5">
                          <span>
                            {formatCompactTimestamp(
                              item.last_activity_at,
                              lang,
                            )}
                          </span>
                          <span className="inline-flex text-subtle">
                            <ChevronIcon direction="right" size={14} />
                          </span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Widok kartowy mobilny (poniżej 768 px, 390 px bez przewijania w poziomie) */}
          <div className="mt-3 flex flex-col gap-2.5 md:hidden">
            {items.map((item) => {
              const emphasized = isRowEmphasized(item);
              const breakdown =
                item.status === "completed"
                  ? formatClaimBreakdown(item, t, lang)
                  : "";
              const caseLabel = displayCaseRef(item);
              return (
                <Link
                  key={item.audit_id}
                  to={`/audyt/${item.audit_id}`}
                  className="block rounded-[10px] bg-white p-3.5 text-text no-underline shadow-[inset_0_0_0_1px_var(--color-border-soft)] transition-colors hover:bg-row-hover"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={
                          "truncate font-mono text-[13px] leading-5 " +
                          (emphasized ? "font-semibold" : "font-normal")
                        }
                      >
                        {caseLabel}
                      </span>
                      {item.is_demo ? (
                        <span className="inline-block flex-none rounded bg-chip px-1.5 py-px font-sans text-[11px] leading-4 font-semibold tracking-[.03em] text-chip-text">
                          {t("analyses.row.demoBadge")}
                        </span>
                      ) : null}
                    </div>
                    <span className="inline-flex flex-none items-center gap-1 text-xs whitespace-nowrap text-muted">
                      <span>
                        {formatCompactTimestamp(item.last_activity_at, lang)}
                      </span>
                      <span className="inline-flex text-subtle">
                        <ChevronIcon direction="right" size={14} />
                      </span>
                    </span>
                  </div>

                  <p
                    className={
                      "mt-1.5 mb-0 line-clamp-2 text-sm leading-5 [overflow-wrap:anywhere] " +
                      (emphasized ? "font-semibold" : "font-normal")
                    }
                  >
                    {item.problem_summary}
                  </p>

                  {item.status === "completed" && item.note_verdict ? (
                    <div className="mt-2.5">
                      <NoteVerdictPill verdict={item.note_verdict} />
                      {breakdown ? (
                        <div className="mt-1 text-xs leading-[18px] text-muted">
                          {breakdown}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="mt-2.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-border-soft pt-2">
                    <DecisionStatusPill
                      variant="inline"
                      status={item.decision_status}
                      auditStatus={item.status}
                      decisionsCount={item.decisions_count}
                      claimsTotal={item.claims_total}
                    />
                    {item.status === "completed" && item.claims_total > 0 ? (
                      <span className="text-xs leading-[18px] text-muted">
                        {t("analyses.row.claimsResolved", {
                          done: item.decisions_count,
                          total: item.claims_total,
                        })}
                      </span>
                    ) : null}
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      ) : null}

      {/* Stopka listy */}
      {state.status === "ready" ? (
        <footer className="mt-3 flex flex-col gap-1.5 border-t border-border-soft pt-2.5 text-xs leading-[18px] text-muted md:flex-row md:items-start md:justify-between md:gap-6 md:px-3">
          <span>{t("analyses.footer.sortOrder")}</span>
          <span className="md:text-right">
            {t("analyses.footer.disclaimer")}
          </span>
        </footer>
      ) : null}
    </div>
  );
}
