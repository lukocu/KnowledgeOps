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
