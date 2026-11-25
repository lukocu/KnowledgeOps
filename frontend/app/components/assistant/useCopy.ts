import { useEffect, useState } from "react";

export type CopyState = "idle" | "copied" | "failed";

/** Kopiowanie do schowka ze stanem wyniku, który po 2 s wraca do `idle`. */
export function useCopy(): {
  state: CopyState;
  copy: (text: string) => Promise<void>;
} {
  const [state, setState] = useState<CopyState>("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return { state, copy };
}
