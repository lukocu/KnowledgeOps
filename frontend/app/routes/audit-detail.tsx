import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/answers";
import { fetchAudit, type AuditDetailResponse } from "../api/audits";
import { InfoIcon } from "../components/assistant/Icon";
import { AuditFormView } from "../components/audit/AuditFormView";
import { AuditProgressAside } from "../components/audit/AuditProgressAside";
import { AuditResultView } from "../components/audit/AuditResultView";
import { useT } from "../i18n/context";

export function meta() {
  return [{ title: "KnowledgeOps" }];
}

const POLL_INTERVAL_MS = 1500;

const PRIMARY_BUTTON =
  "inline-flex h-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-primary px-4 text-sm font-medium whitespace-nowrap text-white no-underline hover:brightness-95";

const SECONDARY_BUTTON =
  "inline-flex h-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-surface px-3.5 text-sm font-medium whitespace-nowrap text-text no-underline hover:brightness-95";

type AuditLoadState =
  | { status: "loading" }
  | { status: "ready"; data: AuditDetailResponse }
  | { status: "not_found" }
  | { status: "error" };

/** Trasa `/audyt/:id`: ekrany 2P (w toku), 3 / 3N (wynik) oraz stan błędu / 404. */
export default function AuditDetailRoute() {
  const { id } = useParams();
  return <AuditDetailScreen key={id} id={id ?? ""} />;
}

function AuditDetailScreen({ id }: { id: string }) {
  const t = useT();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<AuditLoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    let timerId: number | undefined;
    let controller = new AbortController();

    async function poll() {
      controller = new AbortController();
      try {
        const data = await fetchAudit(id, controller.signal);
        if (!active) return;
        setState({ status: "ready", data });
        if (data.status === "queued" || data.status === "running") {
          timerId = window.setTimeout(() => {
            void poll();
          }, POLL_INTERVAL_MS);
        }
      } catch (error: unknown) {
        if (!active || controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) {
          setState({ status: "not_found" });
        } else {
          setState({ status: "error" });
        }
      }
    }

    void poll();

    return () => {
      active = false;
      if (timerId !== undefined) window.clearTimeout(timerId);
      controller.abort();
    };
  }, [id, attempt]);

  if (state.status === "loading") {
    return (
      <div className="px-4 py-6 md:px-6 lg:px-10 lg:py-8">
        <p role="status" className="m-0 text-[15px] leading-6 text-muted">
          {t("audit.detail.loading")}
        </p>
      </div>
    );
  }

  if (state.status === "not_found") {
    return (
      <section className="px-4 py-6 md:px-6 lg:px-10 lg:py-8">
        <div className="flex items-center gap-2.5">
          <InfoIcon size={24} className="flex-none text-icon" />
          <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
            {t("audit.detail.notFoundTitle")}
          </h1>
        </div>
        <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
          {t("audit.detail.notFoundBody")}
        </p>
        <div className="mt-5">
          <Link to="/audyt" className={PRIMARY_BUTTON}>
            {t("audit.detail.newAudit")}
          </Link>
        </div>
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section role="alert" className="px-4 py-6 md:px-6 lg:px-10 lg:py-8">
        <div className="flex items-center gap-2.5">
          <InfoIcon size={24} className="flex-none text-icon" />
          <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
            {t("audit.detail.failedTitle")}
          </h1>
        </div>
        <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
          {t("errorState.internal")}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => {
              setState({ status: "loading" });
              setAttempt((value) => value + 1);
            }}
            className={PRIMARY_BUTTON}
          >
            {t("errorState.retry")}
          </button>
          <Link to="/audyt" className={SECONDARY_BUTTON}>
            {t("audit.detail.newAudit")}
          </Link>
        </div>
      </section>
    );
  }

  const audit = state.data;

  if (audit.status === "queued" || audit.status === "running") {
    return (
      <AuditFormView
        values={{
          caseRef: audit.case_ref ?? "",
          caseDescription: audit.case_description,
          resolutionNote: audit.resolution_note,
        }}
        mode="running"
        aside={<AuditProgressAside audit={audit} />}
      />
    );
  }

  if (audit.status === "failed") {
    return (
      <section role="alert" className="px-4 py-6 md:px-6 lg:px-10 lg:py-8">
        <div className="flex items-center gap-2.5">
          <InfoIcon size={24} className="flex-none text-icon" />
          <h1 className="m-0 text-[22px] leading-[30px] font-semibold">
            {t("audit.detail.failedTitle")}
          </h1>
        </div>
        <p className="mt-2.5 mb-0 max-w-[680px] text-[15px] leading-6">
          {t("audit.detail.failedBody")}
        </p>
        {audit.error ? (
          <p className="mt-2.5 mb-0 max-w-[680px] rounded-lg bg-surface px-3.5 py-2.5 font-mono text-xs leading-5 [overflow-wrap:anywhere] text-secondary">
            {audit.error}
          </p>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            to="/audyt"
            state={{
              caseRef: audit.case_ref ?? "",
              caseDescription: audit.case_description,
              resolutionNote: audit.resolution_note,
            }}
            className={PRIMARY_BUTTON}
          >
            {t("audit.detail.retryAudit")}
          </Link>
          <Link to="/audyt" className={SECONDARY_BUTTON}>
            {t("audit.detail.newAudit")}
          </Link>
        </div>
      </section>
    );
  }

  return <AuditResultView audit={audit} />;
}
