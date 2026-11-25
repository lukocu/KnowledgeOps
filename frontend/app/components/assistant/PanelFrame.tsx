import { useLayoutEffect, useRef, type ReactNode } from "react";

import { useMediaQuery, WIDE_QUERY } from "../../lib/use-media-query";

export type PanelVariant = "evidence" | "checked";

/** Szeroki `aside` (S1A/S1C): szerokość i tło zależą od wariantu, jak dotąd. */
const ASIDE_CLASS: Record<PanelVariant, string> = {
  evidence:
    "flex w-[min(400px,45%)] min-w-[300px] flex-none flex-col overflow-hidden border-l border-border-soft bg-white",
  checked:
    "flex w-[min(420px,45%)] min-w-[300px] flex-none flex-col overflow-hidden border-l border-border-soft bg-surface-alt",
};

const SHEET_BACKGROUND: Record<PanelVariant, string> = {
  evidence: "bg-white",
  checked: "bg-surface-alt",
};

/**
 * Obudowa panelu bocznego: od 768 px `aside` po prawej, poniżej modalny arkusz
 * od dołu (1N). Renderowana raz wokół całego panelu, więc arkusz żyje przez
 * całe otwarcie, także przy przejściu lista sprawdzonych fragmentów ↔ fragment.
 */
export function PanelFrame({
  label,
  variant,
  onDismiss,
  children,
}: {
  label: string;
  variant: PanelVariant;
  onDismiss: () => void;
  children: ReactNode;
}) {
  const wide = useMediaQuery(WIDE_QUERY);

  if (wide) {
    return (
      <aside aria-label={label} className={ASIDE_CLASS[variant]}>
        {children}
      </aside>
    );
  }
  return (
    <PanelSheet label={label} variant={variant} onDismiss={onDismiss}>
      {children}
    </PanelSheet>
  );
}

function PanelSheet({
  label,
  variant,
  onDismiss,
  children,
}: {
  label: string;
  variant: PanelVariant;
  onDismiss: () => void;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Efekt układu: `close()` w sprzątaniu działa, zanim React usunie element z DOM,
  // więc przeglądarka przywraca fokus na element sprzed otwarcia; trasa ustawia
  // go potem jeszcze raz w `requestAnimationFrame`.
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
      aria-label={label}
      onCancel={(event) => {
        // Escape obsługuje trasa (kolejność zamykania i powrót fokusu).
        event.preventDefault();
      }}
      // Natywne zamknięcie mimo `preventDefault()` synchronizuje stan. Zdarzenie `close`
      // przychodzi asynchronicznie; jeśli dialog jest już znowu otwarty (podwójny efekt
      // w StrictMode), to echo wcześniejszego `close()` i je pomijamy.
      onClose={() => {
        if (!dialogRef.current?.open) onDismiss();
      }}
      onClick={(event) => {
        // Klik w tło: celem jest sam dialog, bo treść wypełnia wewnętrzny kontener.
        if (event.target === event.currentTarget) onDismiss();
      }}
      className={
        "fixed inset-x-0 top-auto bottom-0 m-0 max-h-[calc(100dvh-140px)] w-full max-w-none flex-col overflow-hidden rounded-t-2xl border-0 p-0 text-text shadow-[0_-8px_24px_rgba(31,32,35,.18)] backdrop:bg-[rgba(31,32,35,.4)] open:flex " +
        SHEET_BACKGROUND[variant]
      }
    >
      {/* Uchwyt tylko wizualny; leży nad treścią, której tło sięga do krawędzi arkusza
          (fragment w wariancie `checked` ma białe tło). Panele dają mu 20 px u góry. */}
      <div
        aria-hidden="true"
        className="absolute top-2 left-1/2 h-1 w-10 -translate-x-1/2 rounded-sm bg-[#d3d0c6]"
      />
      {children}
    </dialog>
  );
}
