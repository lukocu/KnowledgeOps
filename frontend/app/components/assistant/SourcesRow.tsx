import type { Citation } from "../../api/answers";
import { useT } from "../../i18n/context";

/** Nagłówek sekcji do pigułki: ostatni nagłówek fragmentu albo „Fragment n”. */
function sectionLabel(
  citation: Citation,
  fallback: (n: number) => string,
): string {
  const heading = citation.headings[citation.headings.length - 1];
  return heading && heading.trim() !== "" ? heading : fallback(citation.n);
}

/**
 * Wiersz źródeł (S1A): dla każdego dokumentu nagłówek „Źródło · <doc_id>” i pigułki
 * z numerami cytatów oraz nazwą sekcji. Pigułka otwiera ten sam panel dowodu co numer.
 */
export function SourcesRow({
  citations,
  activeN,
  onOpen,
}: {
  citations: Citation[];
  activeN: number | null;
  onOpen: (n: number, trigger: HTMLButtonElement) => void;
}) {
  const t = useT();
  const fallback = (n: number) => t("answer.sourceFallback", { n });

  const byDocument = new Map<string, Citation[]>();
  for (const citation of citations) {
    const group = byDocument.get(citation.doc_id) ?? [];
    group.push(citation);
    byDocument.set(citation.doc_id, group);
  }

  return (
    <div className="mt-4 flex flex-col gap-2">
      {[...byDocument].map(([docId, group]) => (
        <div key={docId} className="flex flex-wrap items-center gap-2">
          <div className="mr-1 text-xs leading-[18px] font-semibold tracking-[.05em] text-muted uppercase">
            {t("answer.source", { doc: docId })}
          </div>
          {group.map((citation) => {
            const active = citation.n === activeN;
            const label = t("citation.label", {
              n: citation.n,
              total: citations.length,
            });
            return (
              <button
                key={citation.n}
                type="button"
                data-citation={citation.n}
                aria-pressed={active}
                aria-label={`${label}: ${sectionLabel(citation, fallback)}`}
                onClick={(event) => onOpen(citation.n, event.currentTarget)}
                className={
                  "inline-flex h-[30px] cursor-pointer items-center gap-2 rounded-[15px] border py-0 pr-3 pl-1 text-[13px] text-text " +
                  (active
                    ? "border-accent bg-source-active"
                    : "border-border bg-white hover:brightness-95")
                }
              >
                <span
                  className={
                    "inline-flex h-[22px] w-[22px] items-center justify-center rounded-full text-xs font-semibold " +
                    (active ? "bg-accent-strong text-white" : "bg-surface")
                  }
                >
                  {citation.n}
                </span>
                <span>{sectionLabel(citation, fallback)}</span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
