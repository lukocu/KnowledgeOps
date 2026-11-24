import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import {
  askQuestion,
  type ErrorEvent,
  type StageEvent,
} from "../../api/answers";

export type AskState =
  | { status: "idle" }
  | { status: "asking"; question: string; stages: StageEvent[] }
  | { status: "failed"; question: string; error: ErrorEvent };

/**
 * Wysyła pytanie i śledzi postęp. Po `result` przechodzi na `/odpowiedz/:id`;
 * opuszczenie widoku przerywa żądanie (`AbortController`).
 */
export function useAsk() {
  const navigate = useNavigate();
  const [state, setState] = useState<AskState>({ status: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const ask = useCallback(
    (question: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ status: "asking", question, stages: [] });

      askQuestion(question, {
        signal: controller.signal,
        onStage: (event) => {
          if (controller.signal.aborted) return;
          setState((previous) =>
            previous.status === "asking"
              ? { ...previous, stages: [...previous.stages, event] }
              : previous,
          );
        },
      }).then(
        (outcome) => {
          if (controller.signal.aborted) return;
          if ("code" in outcome) {
            setState({ status: "failed", question, error: outcome });
          } else {
            void navigate(`/odpowiedz/${outcome.answer_id}`);
          }
        },
        () => {
          // Przerwanie (opuszczenie widoku lub nowe pytanie) nie zmienia stanu.
        },
      );
    },
    [navigate],
  );

  return { state, ask };
}
