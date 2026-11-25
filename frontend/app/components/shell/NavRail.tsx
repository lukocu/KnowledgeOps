import { useLayoutEffect, useRef, useState } from "react";
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

/**
 * Pozycje nawigacji (`NAV_ITEMS`): jedna lista dla szyny i szuflady.
 * `icons` to szyna 56 px (S1A), `labels` to lista z podpisami (S1P, szuflada).
 */
function NavItems({
  variant,
  onNavigate,
}: {
  variant: "icons" | "labels";
  onNavigate?: () => void;
}) {
  const t = useT();

  if (variant === "icons") {
    return (
      <nav aria-label={t("nav.labelRail")} className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end
            aria-label={t(item.label)}
            title={t(item.label)}
            onClick={onNavigate}
            className={({ isActive }) =>
              "flex h-10 w-10 items-center justify-center rounded-lg text-text " +
              (isActive ? "bg-nav-active" : "bg-transparent")
            }
          >
            {item.icon}
          </NavLink>
        ))}
      </nav>
    );
  }

  return (
    <nav aria-label={t("nav.label")} className="flex flex-col gap-0.5">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end
          onClick={onNavigate}
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
  );
}

/** Szyna nawigacji w szerokim oknie (od 768 px). */
export function NavRail() {
  const t = useT();
  const [expanded, setExpanded] = useState(false);

  if (!expanded) {
    // Szyna 56 px (S1A).
    return (
      <aside className="flex w-14 flex-none flex-col items-center justify-between bg-surface-alt py-3">
        <NavItems variant="icons" />
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
      <NavItems variant="labels" />
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

/**
 * Szuflada nawigacji w wąskim oknie (1N): modalny `<dialog>` z lewej.
 * Otwierany przez `showModal()` po zamontowaniu, zamykany przez odmontowanie.
 */
export function NavDrawer({
  id,
  open,
  onClose,
}: {
  id?: string;
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;
  return <NavDrawerDialog id={id} onClose={onClose} />;
}

function NavDrawerDialog({
  id,
  onClose,
}: {
  id?: string;
  onClose: () => void;
}) {
  const t = useT();
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Efekt układu: `close()` w sprzątaniu działa, zanim React usunie element z DOM,
  // więc przeglądarka przywraca fokus na przycisk Menu.
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      id={id}
      aria-label={t("nav.label")}
      onCancel={(event) => {
        // Escape: zamknięcie przez stan Reacta, nie natywnie.
        event.preventDefault();
        onClose();
      }}
      // Natywne zamknięcie mimo `preventDefault()` (np. powtórzony Escape) synchronizuje stan.
      // Zdarzenie `close` przychodzi asynchronicznie; jeśli dialog jest już znowu otwarty
      // (podwójny efekt w StrictMode), to echo wcześniejszego `close()` i je pomijamy.
      onClose={() => {
        if (!dialogRef.current?.open) onClose();
      }}
      onClick={(event) => {
        // Klik w tło: celem jest sam dialog, bo treść wypełnia wewnętrzny kontener.
        if (event.target === event.currentTarget) onClose();
      }}
      className="fixed inset-y-0 right-auto left-0 m-0 h-full max-h-none w-[min(280px,85vw)] max-w-none border-0 bg-surface-alt p-0 text-text shadow-[8px_0_24px_rgba(31,32,35,.18)] backdrop:bg-[rgba(31,32,35,.4)]"
    >
      <div className="flex h-full flex-col px-2.5 pt-2 pb-4">
        <div className="flex flex-none justify-end">
          <button
            type="button"
            aria-label={t("nav.close")}
            title={t("nav.close")}
            onClick={onClose}
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted"
          >
            <svg {...ICON_PROPS}>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div className="mt-1 min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <NavItems variant="labels" onNavigate={onClose} />
        </div>
        <p className="m-0 mt-3 flex-none px-2.5 text-xs leading-[18px] text-muted">
          {t("nav.dataSource")}
        </p>
      </div>
    </dialog>
  );
}
