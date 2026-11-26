import { useEffect, useRef } from "react";

import type { CaseContext } from "../../api/audits";
import { useT } from "../../i18n/context";
import { CloseIcon } from "../assistant/Icon";

function ContextField({
  label,
  value,
  fallback,
}: {
  label: string;
  value: string | null | undefined;
  fallback: string;
}) {
  const clean = value?.trim();
  return (
    <div className="border-b border-border-soft py-3">
      <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
        {label}
      </div>
      <p
        className={
          "mt-1 mb-0 text-sm leading-[22px] [overflow-wrap:anywhere] whitespace-pre-wrap " +
          (clean ? "text-text" : "text-muted italic")
        }
      >
        {clean || fallback}
      </p>
    </div>
  );
}

function ContextList({
  label,
  items,
  emptyText,
}: {
  label: string;
  items: readonly string[];
  emptyText: string;
}) {
  return (
    <div className="border-b border-border-soft py-3">
      <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
        {label}
      </div>
      {items.length > 0 ? (
        <ul className="mt-1.5 mb-0 list-disc pl-5 text-sm leading-[22px] text-text">
          {items.map((item, index) => (
            <li key={`${index}-${item}`} className="[overflow-wrap:anywhere]">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 mb-0 text-sm leading-[22px] text-muted">
          {emptyText}
        </p>
      )}
    </div>
  );
}

/**
 * Panel „Kontekst sprawy” (FR-007 + decyzja D4): pola wyodrębnione ze sprawy oraz
 * oryginalny opis zgłoszenia. Renderowany w `PanelFrame` (wspólny slot z `EvidencePanel`).
 */
export function CaseContextPanel({
  caseContext,
  caseDescription,
  onClose,
}: {
  caseContext: CaseContext | null;
  caseDescription: string;
  onClose: () => void;
}) {
  const t = useT();
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  const notProvided = t("audit.context.notProvided");
  const none = t("audit.context.none");

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain bg-surface-alt px-[16px] pt-5 pb-4 md:px-6 md:pt-3">
      <div className="flex items-center justify-between">
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="m-0 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase"
        >
          {t("audit.context.panelLabel")}
        </h2>
        <button
          type="button"
          aria-label={t("audit.context.close")}
          title={t("audit.context.close")}
          onClick={onClose}
          className="inline-flex h-[40px] w-[40px] cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted hover:bg-surface md:h-8 md:w-8"
        >
          <CloseIcon />
        </button>
      </div>

      <div className="mt-2">
        <ContextField
          label={t("audit.context.problem")}
          value={caseContext?.problem}
          fallback={notProvided}
        />
        <ContextField
          label={t("audit.context.environment")}
          value={caseContext?.environment}
          fallback={notProvided}
        />
        <ContextField
          label={t("audit.context.solution")}
          value={caseContext?.solution}
          fallback={notProvided}
        />
        <ContextList
          label={t("audit.context.constraints")}
          items={caseContext?.constraints ?? []}
          emptyText={none}
        />
        <ContextList
          label={t("audit.context.missingInfo")}
          items={caseContext?.missing_info ?? []}
          emptyText={none}
        />
        <div className="py-3">
          <div className="text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
            {t("audit.context.originalDescription")}
          </div>
          <div className="mt-1.5 rounded-lg bg-white px-3.5 py-2.5 text-sm leading-[22px] [overflow-wrap:anywhere] whitespace-pre-wrap text-text shadow-[inset_0_0_0_1px_var(--color-border-soft)]">
            {caseDescription}
          </div>
        </div>
      </div>
    </div>
  );
}
