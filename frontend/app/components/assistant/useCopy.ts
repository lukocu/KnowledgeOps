import { useEffect, useRef, useState } from "react";

export type CopyState = "idle" | "copied" | "failed";

/** Kopiowanie do schowka ze stanem wyniku, który po 2 s wraca do `idle`. */
export function useCopy(): {
  state: CopyState;
  copy: (text: string) => Promise<void>;
} {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy(text: string) {
    let result: CopyState;
    try {
      await navigator.clipboard.writeText(text);
      result = "copied";
    } catch {
      result = "failed";
    }
    setState(result);
    // Każde kopiowanie restartuje odliczanie 2 s.
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2000);
  }

  return { state, copy };
}
