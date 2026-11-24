import type { StageEvent } from "../api/answers";

/** Trzy kroki karty postępu, każdy obejmuje etapy grafu backendu. */
export type StepId = "search" | "check" | "compose";
export type StepStatus = "pending" | "active" | "done";
export type Step = { id: StepId; status: StepStatus };

const STEP_STAGES: Record<StepId, StageEvent["stage"][]> = {
  search: ["retrieve"],
  check: ["draft", "quote_check", "verify"],
  compose: ["compose"],
};

const STEP_ORDER: StepId[] = ["search", "check", "compose"];

/**
 * Stan kroków wynika wyłącznie z odebranych zdarzeń `stage`:
 * - krok trwa od pierwszego zdarzenia `started` jego etapów,
 * - jest zakończony, gdy skończył się jego ostatni etap albo gdy zaczął się etap
 *   z późniejszego kroku (także `abstain`, który omija pozostałe kroki).
 * Krok bez żadnego zdarzenia pozostaje „oczekuje”.
 */
export function deriveSteps(events: readonly StageEvent[]): Step[] {
  const abstainStarted = events.some((e) => e.stage === "abstain");

  return STEP_ORDER.map((id, index) => {
    const stages = STEP_STAGES[id];
    const own = events.filter((e) => stages.includes(e.stage));
    if (own.length === 0) return { id, status: "pending" };

    const lastStage = stages[stages.length - 1];
    const finished = own.some(
      (e) => e.stage === lastStage && e.status === "done",
    );
    const later = STEP_ORDER.slice(index + 1).some((next) =>
      events.some((e) => STEP_STAGES[next].includes(e.stage)),
    );
    return {
      id,
      status: finished || later || abstainStarted ? "done" : "active",
    };
  });
}
