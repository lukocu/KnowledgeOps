import { useId } from "react";

import { useT } from "../../i18n/context";

export function DemoBadge() {
  const t = useT();
  const noticeId = useId();

  return (
    <>
      {/* tabIndex: opis (title) ma być osiągalny z klawiatury i czytnika ekranu. */}
      <span
        tabIndex={0}
        aria-describedby={noticeId}
        title={t("header.demoNotice")}
        className="inline-flex cursor-help items-center gap-[5px] rounded-md bg-chip px-2 py-px text-xs leading-5 font-semibold tracking-[.04em] whitespace-nowrap text-chip-text"
      >
        {t("header.demo")}
        <svg
          aria-hidden="true"
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="flex-none"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5" />
          <path d="M12 8h.01" />
        </svg>
      </span>
      <span id={noticeId} className="sr-only">
        {t("header.demoNotice")}
      </span>
    </>
  );
}
