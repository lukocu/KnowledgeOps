import type { ReactNode } from "react";

/** Ikony liniowe z kanwy (viewBox 24, kreska 1.8). Zawsze dekoracyjne: znaczenie niesie tekst. */
export function Icon({
  size = 16,
  stroke = "currentColor",
  className = "flex-none",
  children,
}: {
  size?: number;
  stroke?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {children}
    </svg>
  );
}

export const CheckIcon = ({
  size,
  stroke,
  className,
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <Icon size={size} stroke={stroke} className={className}>
    <path d="M5 12l5 5 9-10" />
  </Icon>
);

export const CopyIcon = () => (
  <Icon>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5 15V6a2 2 0 0 1 2-2h9" />
  </Icon>
);

export const InfoIcon = ({
  size,
  stroke,
  className,
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <Icon size={size} stroke={stroke} className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5" />
    <path d="M12 8h.01" />
  </Icon>
);

export const CloseIcon = () => (
  <Icon size={18}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

/** Ikona stanu „Sprzeczność” (✕, kanwa S5). Zawsze dekoracyjna obok etykiety tekstowej. */
export const ContradictionIcon = ({
  size = 15,
  stroke = "currentColor",
  className = "flex-none",
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <svg
    aria-hidden="true"
    width={size}
    height={size}
    viewBox="0 0 16 16"
    fill="none"
    stroke={stroke}
    strokeWidth={1.8}
    strokeLinecap="round"
    className={className}
  >
    <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
  </svg>
);

/** Ikona stanu „Poparta” / „Pełne pokrycie” (●, kanwa S3). */
export const SupportedIcon = ({
  size = 14,
  className = "flex-none",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    aria-hidden="true"
    width={size}
    height={size}
    viewBox="0 0 16 16"
    className={className}
  >
    <circle cx="8" cy="8" r="6" fill="currentColor" />
  </svg>
);

/** Ikona stanu „Częściowe pokrycie” (◐, kanwa S3). */
export const PartialIcon = ({
  size = 15,
  className = "flex-none",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    aria-hidden="true"
    width={size}
    height={size}
    viewBox="0 0 16 16"
    className={className}
  >
    <circle
      cx="8"
      cy="8"
      r="5.4"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
    />
    <path d="M8 2.6a5.4 5.4 0 0 0 0 10.8z" fill="currentColor" />
  </svg>
);

/** Ikona stanu „Niewystarczające dowody” (przerywane kółko ze znakiem zapytania, kanwa 1C/S3). */
export const InsufficientIcon = ({
  size = 15,
  className = "flex-none",
}: {
  size?: number;
  className?: string;
}) => (
  <svg
    aria-hidden="true"
    width={size}
    height={size}
    viewBox="0 0 16 16"
    className={className}
  >
    <circle
      cx="8"
      cy="8"
      r="6"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeDasharray="2.2 1.8"
    />
    <path
      d="M6.4 6.4a1.7 1.7 0 1 1 2.3 1.6c-.5.2-.7.5-.7 1v.3"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.3}
      strokeLinecap="round"
    />
    <circle cx="8" cy="11.1" r=".8" fill="currentColor" />
  </svg>
);

/** Ikona oceny automatycznej systemu (kanwa S3). */
export const SystemIcon = ({
  size = 16,
  stroke,
  className,
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <Icon size={size} stroke={stroke} className={className}>
    <rect x="5" y="8" width="14" height="11" rx="3" />
    <path d="M12 4v4" />
    <path d="M9.5 13h.01M14.5 13h.01" />
  </Icon>
);

/** Ikona człowieka / decyzji redaktora (kanwa S3/S3N/S3ND). */
export const PersonIcon = ({
  size = 18,
  stroke,
  className,
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <Icon size={size} stroke={stroke} className={className}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
  </Icon>
);

/** Ikona nawigacji audytu (clipboard-check, kanwa S2). */
export const AuditNavIcon = ({
  size = 18,
  stroke,
  className,
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <Icon size={size} stroke={stroke} className={className}>
    <rect x="5" y="4" width="14" height="17" rx="2" />
    <path d="M9 4h6v3H9z" />
    <path d="M9 13l2 2 4-4" />
  </Icon>
);

/** Ikona otwarcia całego dokumentu (kanwa S3). */
export const ExternalLinkIcon = ({
  size = 16,
  stroke,
  className,
}: {
  size?: number;
  stroke?: string;
  className?: string;
}) => (
  <Icon size={size} stroke={stroke} className={className}>
    <path d="M14 4h6v6" />
    <path d="M20 4l-9 9" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Icon>
);

/** Wspólna ikona stanu kroku w kartach postępu (1P i 2P). */
export function StepStatusIcon({
  status,
}: {
  status: "pending" | "active" | "done";
}) {
  if (status === "done") {
    return <CheckIcon size={18} className="flex-none text-success" />;
  }
  if (status === "active") {
    return (
      <svg
        aria-hidden="true"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="flex-none animate-spin text-primary"
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

export const ChevronIcon = ({
  direction,
  size = 18,
}: {
  direction: "left" | "right" | "up" | "down";
  size?: number;
}) => {
  const paths = {
    left: "M15 6l-6 6 6 6",
    right: "M9 6l6 6-6 6",
    up: "M6 15l6-6 6 6",
    down: "M6 9l6 6 6-6",
  } as const;
  return (
    <Icon size={size}>
      <path d={paths[direction]} />
    </Icon>
  );
};
