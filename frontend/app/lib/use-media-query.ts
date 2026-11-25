import { useCallback, useSyncExternalStore } from "react";

/** Szerokie okno: próg zgodny z breakpointem Tailwind `md` (768 px). */
export const WIDE_QUERY = "(min-width: 768px)";

/**
 * Czy zapytanie CSS media pasuje do okna. Rerender tylko przy zmianie wyniku,
 * nie przy każdej zmianie rozmiaru. Komponenty, które zmieniają element albo
 * zachowanie (szuflada, arkusz), pytają tego hooka; czysto wizualne różnice
 * robią klasy `md:`.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );

  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    // SPA (`ssr: false`) renderuje w przeglądarce; przy prerenderze zakładamy szerokie okno.
    () => true,
  );
}
