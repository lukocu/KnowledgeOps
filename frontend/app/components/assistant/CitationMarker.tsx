import type { Ref } from "react";

import { useT } from "../../i18n/context";

/** Numer cytatu jako przycisk (S1A): aktywny cytat ma wypełnione tło mocnego akcentu. */
export function CitationMarker({
  n,
  total,
  active,
  onOpen,
  ref,
}: {
  n: number;
  total: number;
  active: boolean;
  onOpen: (trigger: HTMLButtonElement) => void;
  ref?: Ref<HTMLButtonElement>;
}) {
  const t = useT();
  const label = t("citation.label", { n, total });

  return (
    <button
      ref={ref}
      type="button"
      data-citation={n}
      aria-label={label}
      aria-pressed={active}
      title={label}
      onClick={(event) => onOpen(event.currentTarget)}
      className={
        "mr-0.5 ml-1.5 box-border inline-flex h-6 w-6 cursor-pointer items-center justify-center rounded-md border p-0 align-middle text-[13px] font-semibold " +
        (active
          ? "border-accent-strong bg-accent-strong text-white"
          : "border-border bg-white text-text hover:brightness-95")
      }
    >
      {n}
    </button>
  );
}
