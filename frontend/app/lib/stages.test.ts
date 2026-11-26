import { describe, expect, it } from "vitest";

import type { StageEvent } from "../api/answers";
import { deriveSteps } from "./stages";

function event(
  stage: StageEvent["stage"],
  status: StageEvent["status"],
): StageEvent {
  return { stage, status };
}

describe("deriveSteps", () => {
  it("zwraca wszystkie kroki jako pending przy braku zdarzeń", () => {
    expect(deriveSteps([])).toEqual([
      { id: "search", status: "pending" },
      { id: "check", status: "pending" },
      { id: "compose", status: "pending" },
    ]);
  });

  it("utrzymuje krok check jako active podczas detect_conflict i kończy go po done", () => {
    const duringDetect = deriveSteps([
      event("retrieve", "started"),
      event("retrieve", "done"),
      event("draft", "started"),
      event("draft", "done"),
      event("quote_check", "started"),
      event("quote_check", "done"),
      event("verify", "started"),
      event("verify", "done"),
      event("detect_conflict", "started"),
    ]);
    expect(duringDetect).toEqual([
      { id: "search", status: "done" },
      { id: "check", status: "active" },
      { id: "compose", status: "pending" },
    ]);

    const afterDetect = deriveSteps([
      event("retrieve", "started"),
      event("retrieve", "done"),
      event("verify", "done"),
      event("detect_conflict", "started"),
      event("detect_conflict", "done"),
    ]);
    expect(afterDetect).toEqual([
      { id: "search", status: "done" },
      { id: "check", status: "done" },
      { id: "compose", status: "pending" },
    ]);
  });

  it("kończy krok check, gdy compose zacznie się bez detect_conflict", () => {
    const steps = deriveSteps([
      event("retrieve", "done"),
      event("verify", "done"),
      event("compose", "started"),
    ]);
    expect(steps).toEqual([
      { id: "search", status: "done" },
      { id: "check", status: "done" },
      { id: "compose", status: "active" },
    ]);
  });

  it("kończy rozpoczęte kroki, gdy rozpocznie się abstain", () => {
    const steps = deriveSteps([
      event("retrieve", "done"),
      event("draft", "started"),
      event("abstain", "started"),
    ]);
    expect(steps).toEqual([
      { id: "search", status: "done" },
      { id: "check", status: "done" },
      { id: "compose", status: "pending" },
    ]);
  });
});
