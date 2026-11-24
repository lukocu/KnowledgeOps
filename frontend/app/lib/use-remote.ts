import { useEffect, useState } from "react";

import { ApiError } from "../api/answers";

export type RemoteState<T> =
  | { status: "loading"; previous: T | undefined }
  | { status: "ready"; data: T }
  | { status: "not_found" }
  | { status: "error" };

type Entry<T> = {
  source: (signal: AbortSignal) => Promise<T>;
  state: { status: "ready"; data: T } | { status: "not_found" | "error" };
};

/**
 * Pobiera dane funkcją `load` (wynik musi być stabilny, np. z `useCallback`): zmiana
 * tożsamości `load` uruchamia nowe żądanie i przerywa poprzednie. W trakcie ładowania
 * zwraca ostatnie udane dane jako `previous`, żeby widok nie migał przy rozwijaniu kontekstu.
 */
export function useRemote<T>(
  load: (signal: AbortSignal) => Promise<T>,
): RemoteState<T> {
  const [entry, setEntry] = useState<Entry<T> | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) {
          setEntry({ source: load, state: { status: "ready", data } });
        }
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const status =
          error instanceof ApiError && error.status === 404
            ? "not_found"
            : "error";
        setEntry({ source: load, state: { status } });
      },
    );
    return () => controller.abort();
  }, [load]);

  if (entry && entry.source === load) return entry.state;
  return {
    status: "loading",
    previous: entry?.state.status === "ready" ? entry.state.data : undefined,
  };
}
