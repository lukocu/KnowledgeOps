import { useEffect, useState } from "react";

import { client } from "../../api/client";
import type { components } from "../../api/schema";
import { useT } from "../../i18n/context";
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

export function AppHeader() {
  const t = useT();
  const corpus = useCorpusInfo();

  return (
    <header className="flex h-11 flex-none items-center gap-4 border-b border-border-soft bg-white px-4">
      <span className="inline-flex items-center gap-2 text-sm font-semibold">
        <svg
          aria-hidden="true"
          width="20"
          height="20"
          viewBox="0 0 20 20"
          className="flex-none"
        >
          <rect
            x="1"
            y="1"
            width="18"
            height="18"
            rx="5"
            className="fill-text"
          />
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
      <RoleSwitch />
      <DemoBadge />
      <LanguageSwitch />
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
    </header>
  );
}
