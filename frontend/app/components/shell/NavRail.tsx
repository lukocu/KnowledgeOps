import { useState } from "react";
import { NavLink } from "react-router";

import { useT } from "../../i18n/context";
import type { TranslationKey } from "../../i18n/pl";

type NavItem = { to: string; label: TranslationKey; icon: React.ReactNode };

const ICON_PROPS = {
  "aria-hidden": true,
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  className: "flex-none",
} as const;

/** Jedna pozycja do S-08/S-10: nie pokazujemy linków prowadzących donikąd. */
const NAV_ITEMS: NavItem[] = [
  {
    to: "/",
    label: "nav.assistant",
    icon: (
      <svg {...ICON_PROPS}>
        <path d="M4 5h16v11H9l-5 4z" />
      </svg>
    ),
  },
];

function Chevron({ direction }: { direction: "right" | "left" }) {
  return (
    <svg {...ICON_PROPS}>
      <path d={direction === "right" ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"} />
    </svg>
  );
}

export function NavRail() {
  const t = useT();
  const [expanded, setExpanded] = useState(false);

  if (!expanded) {
    // Szyna 56 px (S1A).
    return (
      <aside className="flex w-14 flex-none flex-col items-center justify-between bg-surface-alt py-3">
        <nav aria-label={t("nav.labelRail")} className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              aria-label={t(item.label)}
              title={t(item.label)}
              className={({ isActive }) =>
                "flex h-10 w-10 items-center justify-center rounded-lg text-text " +
                (isActive ? "bg-nav-active" : "bg-transparent")
              }
            >
              {item.icon}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          aria-label={t("nav.expand")}
          aria-expanded={false}
          title={t("nav.expand")}
          onClick={() => setExpanded(true)}
          className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted"
        >
          <Chevron direction="right" />
        </button>
      </aside>
    );
  }

  // Rozwinięta nawigacja 232 px (S1P).
  return (
    <aside className="flex w-[232px] flex-none flex-col justify-between bg-surface-alt px-2.5 pt-3 pb-4">
      <nav aria-label={t("nav.label")} className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end
            className={({ isActive }) =>
              "flex min-h-9 items-center gap-3 rounded-lg px-2.5 py-1.5 text-sm leading-5 text-text no-underline " +
              (isActive
                ? "bg-nav-active font-semibold"
                : "bg-transparent font-normal")
            }
          >
            {item.icon}
            <span>{t(item.label)}</span>
          </NavLink>
        ))}
      </nav>
      <div className="flex flex-col gap-3">
        <p className="m-0 px-2.5 text-xs leading-[18px] text-muted">
          {t("nav.dataSource")}
        </p>
        <button
          type="button"
          aria-label={t("nav.collapse")}
          aria-expanded={true}
          title={t("nav.collapse")}
          onClick={() => setExpanded(false)}
          className="ml-2.5 inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted"
        >
          <Chevron direction="left" />
        </button>
      </div>
    </aside>
  );
}
