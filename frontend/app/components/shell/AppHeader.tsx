import { useEffect, useState } from "react";

import { client } from "../../api/client";
import type { components } from "../../api/schema";
import { useT } from "../../i18n/context";
import { useMediaQuery, WIDE_QUERY } from "../../lib/use-media-query";
import { DemoBadge } from "./DemoBadge";
import { LanguageSwitch } from "./LanguageSwitch";
import { RoleSwitch } from "./RoleSwitch";

type CorpusInfo = components["schemas"]["CorpusInfo"];

/** Migawka korpusu z GET /api/corpus; `null`, gdy endpoint zawiedzie (neutralny tekst). */
function useCorpusInfo(): CorpusInfo | null {
  const [corpus, setCorpus] = useState<CorpusInfo | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    client
      .GET("/api/corpus", { signal: controller.signal })
      .then(({ data }) => {
        if (data && !controller.signal.aborted) setCorpus(data);
      })
      .catch(() => {
        // Brak backendu lub przerwane żądanie: nagłówek działa bez migawki.
      });
    return () => controller.abort();
  }, []);

  return corpus;
}

function Logo({ narrow }: { narrow: boolean }) {
  const t = useT();
  return (
    <span
      className={
        "inline-flex items-center gap-2 font-semibold " +
        (narrow ? "text-[15px]" : "text-sm")
      }
    >
      <svg
        aria-hidden="true"
        width="20"
        height="20"
        viewBox="0 0 20 20"
        className="flex-none"
      >
        <rect x="1" y="1" width="18" height="18" rx="5" className="fill-text" />
        <path
          d="M6 6.5h8M6 10h5"
          stroke="#fff"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M6 13.8h8"
          className="stroke-accent"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
      </svg>
      {t("app.name")}
    </span>
  );
}

export function AppHeader({
  onOpenMenu,
  menuOpen,
  menuId,
}: {
  onOpenMenu: () => void;
  menuOpen: boolean;
  menuId: string;
}) {
  const t = useT();
  const corpus = useCorpusInfo();
  const wide = useMediaQuery(WIDE_QUERY);

  const corpusLabel = (
    <span
      className="ml-auto text-[13px] text-muted"
      title={
        corpus
          ? t("header.corpusSnapshot", { revision: corpus.revision_short })
          : undefined
      }
    >
      {t("header.corpus")}
    </span>
  );

  if (wide) {
    return (
      <header className="flex h-11 flex-none items-center gap-4 border-b border-border-soft bg-white px-4">
        <Logo narrow={false} />
        <RoleSwitch />
        <DemoBadge />
        <LanguageSwitch />
        {corpusLabel}
      </header>
    );
  }

  // Wąskie okno (1N): dwa rzędy, żaden element nie znika.
  return (
    <header className="flex flex-none flex-col gap-2 border-b border-border-soft bg-white px-[16px] pt-2 pb-2.5">
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label={t("nav.menu")}
          title={t("nav.menu")}
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? menuId : undefined}
          aria-haspopup="dialog"
          onClick={onOpenMenu}
          className="inline-flex h-[36px] w-[36px] flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent p-0 text-muted"
        >
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
            className="flex-none"
          >
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
        <Logo narrow />
        <span className="ml-auto inline-flex items-center gap-2">
          <DemoBadge />
          <LanguageSwitch />
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <RoleSwitch />
        {corpusLabel}
      </div>
    </header>
  );
}
