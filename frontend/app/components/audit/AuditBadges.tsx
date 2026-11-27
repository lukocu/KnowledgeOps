import type {
  AuditStatus,
  ClaimVerdict,
  DecisionStatus,
  NoteVerdict,
} from "../../api/audits";
import { useT } from "../../i18n/context";
import {
  CLAIM_VERDICT_LABEL,
  DECISION_STATUS_LABEL,
  NOTE_VERDICT_LABEL,
} from "../../lib/audit";
import {
  CheckIcon,
  ContradictionIcon,
  InfoIcon,
  InsufficientIcon,
  PartialIcon,
  PersonIcon,
  StepStatusIcon,
  SupportedIcon,
} from "../assistant/Icon";

/** Pigułka oceny całej notatki (zawsze słowo i ikona; brak dowodu szary, nigdy czerwony). */
export function NoteVerdictPill({ verdict }: { verdict: NoteVerdict }) {
  const t = useT();
  const styles: Record<NoteVerdict, string> = {
    full: "bg-supported-bg text-supported-text",
    partial: "bg-partial-bg text-partial-text",
    contradiction: "bg-conflict-bg text-conflict-text",
    insufficient: "bg-insufficient-bg text-insufficient-text",
  };
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full py-[3px] pr-3 pl-2.5 text-[13px] leading-[22px] font-semibold whitespace-nowrap " +
        styles[verdict]
      }
    >
      {verdict === "full" ? (
        <SupportedIcon size={14} className="flex-none text-supported-icon" />
      ) : verdict === "partial" ? (
        <PartialIcon size={15} className="flex-none text-partial-icon" />
      ) : verdict === "contradiction" ? (
        <ContradictionIcon size={14} className="flex-none text-conflict-icon" />
      ) : (
        <InsufficientIcon size={15} className="flex-none text-icon" />
      )}
      {t(NOTE_VERDICT_LABEL[verdict])}
    </span>
  );
}

/** Pigułka oceny pojedynczej tezy (zawsze słowo i ikona; brak dowodu szary). */
export function ClaimVerdictPill({
  verdict,
  size = "sm",
}: {
  verdict: ClaimVerdict;
  size?: "sm" | "md";
}) {
  const t = useT();
  const styles: Record<ClaimVerdict, string> = {
    supported: "bg-supported-bg text-supported-text",
    contradicted: "bg-conflict-bg text-conflict-text",
    insufficient: "bg-insufficient-bg text-insufficient-text",
  };
  const textSize = size === "md" ? "text-sm" : "text-xs";
  const iconSize = size === "md" ? 16 : 14;
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full py-[3px] pr-3 pl-2.5 leading-[22px] font-semibold whitespace-nowrap " +
        textSize +
        " " +
        styles[verdict]
      }
    >
      {verdict === "supported" ? (
        <SupportedIcon
          size={iconSize}
          className="flex-none text-supported-icon"
        />
      ) : verdict === "contradicted" ? (
        <ContradictionIcon
          size={iconSize}
          className="flex-none text-conflict-icon"
        />
      ) : (
        <InsufficientIcon size={iconSize} className="flex-none text-icon" />
      )}
      {t(CLAIM_VERDICT_LABEL[verdict])}
    </span>
  );
}

/**
 * Zbiorcza pigułka lub status liniowy decyzji redaktora (oddzielny od oceny systemu).
 * Obsługuje również stany trwania (`queued`/`running`) i błędu (`failed`) zadania w tle.
 */
export function DecisionStatusPill({
  status,
  auditStatus = "completed",
  decisionsCount,
  claimsTotal,
  variant = "pill",
}: {
  status: DecisionStatus;
  auditStatus?: AuditStatus;
  decisionsCount: number;
  claimsTotal: number;
  variant?: "pill" | "inline";
}) {
  const t = useT();

  if (auditStatus === "queued" || auditStatus === "running") {
    if (variant === "inline") {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm leading-5 text-text">
          <StepStatusIcon status="active" />
          <span>{t("analyses.status.running")}</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-surface py-[3px] pr-3 pl-2.5 text-[13px] leading-[22px] font-semibold whitespace-nowrap text-text">
        <StepStatusIcon status="active" />
        {t("analyses.status.running")}
      </span>
    );
  }

  if (auditStatus === "failed") {
    if (variant === "inline") {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm leading-5 font-medium text-conflict-text">
          <InfoIcon size={16} className="flex-none text-conflict-icon" />
          <span>{t("analyses.status.failed")}</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-conflict-bg py-[3px] pr-3 pl-2.5 text-[13px] leading-[22px] font-semibold whitespace-nowrap text-conflict-text">
        <InfoIcon size={14} className="flex-none text-conflict-icon" />
        {t("analyses.status.failed")}
      </span>
    );
  }

  if (variant === "inline") {
    if (status === "pending") {
      return (
        <span className="inline-flex items-center gap-2 text-sm leading-5 font-semibold text-text">
          <span
            aria-hidden="true"
            className="h-2 w-2 flex-none rounded-full bg-primary"
          />
          <span>{t("analyses.decision.pending")}</span>
        </span>
      );
    }
    if (status === "in_progress") {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm leading-5 font-semibold text-text">
          <PartialIcon size={15} className="flex-none text-partial-icon" />
          <span>{t("analyses.decision.in_progress")}</span>
        </span>
      );
    }
    if (status === "saved") {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm leading-5 text-text">
          <CheckIcon size={16} className="flex-none text-success" />
          <span>{t("analyses.decision.saved")}</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 text-sm leading-5 text-muted">
        <InfoIcon size={15} className="flex-none text-muted" />
        <span>{t("analyses.decision.not_applicable")}</span>
      </span>
    );
  }

  if (status === "not_applicable") return null;

  const isSaved = status === "saved";
  const isInProgress = status === "in_progress";
  const label = t(DECISION_STATUS_LABEL[status], {
    done: decisionsCount,
    total: claimsTotal,
  });

  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full py-[3px] pr-3 pl-2.5 text-[13px] leading-[22px] font-semibold whitespace-nowrap " +
        (isSaved
          ? "bg-supported-bg text-supported-text"
          : isInProgress
            ? "bg-surface text-text"
            : "bg-surface text-muted")
      }
    >
      {isSaved ? (
        <SupportedIcon size={14} className="flex-none text-supported-icon" />
      ) : (
        <PersonIcon
          size={14}
          className={"flex-none " + (isInProgress ? "text-icon" : "text-muted")}
        />
      )}
      {label}
    </span>
  );
}
