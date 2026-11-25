import { describe, expect, it } from "vitest";

import type { AnsweredResult, Citation } from "../api/answers";
import { formatAnswerForCopy } from "./copy-answer";

const labels = { sources: "Sources", snapshot: "Snapshot" };
const snapshotId = "techqa@0b5bbc8f2d4e6a1c";

function citation(n: number, docId: string, title: string): Citation {
  return {
    n,
    doc_id: docId,
    title,
    chunk_id: `chunk-${n}`,
    headings: [],
    claims: [],
  };
}

const result: AnsweredResult = {
  outcome: "answered",
  claims: [
    {
      text: "Jobs started as a system service may not inherit .bashrc.",
      citation: 1,
      code: null,
    },
    {
      text: "Set the variables directly in the instance:",
      citation: 2,
      code: "streamtool setproperty -d <domain> \\\n  --application-ev ODBCINI=<path>",
    },
    {
      text: "The error is SQL state 08003.",
      citation: 1,
      code: null,
    },
  ],
  // Celowo nie po kolei: lista źródeł ma być posortowana po `n`.
  citations: [
    citation(2, "swg21996508", "Problem Solution"),
    citation(1, "swg21996508", "ABSTRACT"),
  ],
  checked_chunks: [],
  omitted_claims: 2,
};

const text = formatAnswerForCopy(result, snapshotId, labels);
const lines = text.split("\n");

describe("formatAnswerForCopy", () => {
  it("kończy każdą tezę numerem jej cytatu", () => {
    for (const claim of result.claims) {
      expect(lines).toContain(`${claim.text} [${claim.citation}]`);
    }
  });

  it("dla każdego [n] ma linię źródła z doc_id", () => {
    for (const claim of result.claims) {
      const source = lines.find((line) =>
        line.startsWith(`[${claim.citation}] `),
      );
      expect(source).toBeDefined();
      expect(source).toContain("swg21996508");
    }
  });

  it("wcina kod pod właściwą tezą", () => {
    const claimLine = lines.indexOf(
      "Set the variables directly in the instance: [2]",
    );
    expect(lines[claimLine + 1]).toBe(
      "    streamtool setproperty -d <domain> \\",
    );
    expect(lines[claimLine + 2]).toBe("      --application-ev ODBCINI=<path>");
    expect(lines[claimLine + 3]).toBe("The error is SQL state 08003. [1]");
  });

  it("daje jedną linię źródła dla dwóch tez z tym samym cytatem", () => {
    expect(lines.filter((line) => line.startsWith("[1] "))).toHaveLength(1);
  });

  it("pomija tezy pominięte", () => {
    const claimLines = lines.slice(0, lines.indexOf(""));
    const withMarker = claimLines.filter((line) => / \[\d+\]$/.test(line));
    expect(withMarker).toHaveLength(result.claims.length);
  });

  it("zwraca oczekiwany tekst dla stałego przykładu", () => {
    expect(text).toBe(
      [
        "Jobs started as a system service may not inherit .bashrc. [1]",
        "Set the variables directly in the instance: [2]",
        "    streamtool setproperty -d <domain> \\",
        "      --application-ev ODBCINI=<path>",
        "The error is SQL state 08003. [1]",
        "",
        "Sources:",
        "[1] swg21996508 — ABSTRACT",
        "[2] swg21996508 — Problem Solution",
        "Snapshot: 0b5bbc8",
        "",
      ].join("\n"),
    );
  });
});
