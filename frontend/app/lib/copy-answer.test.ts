import { describe, expect, it } from "vitest";

import type {
  AnsweredResult,
  Citation,
  ConflictingResult,
} from "../api/answers";
import {
  formatAnswerForCopy,
  formatConflictForCopy,
  type ConflictCopyLabels,
} from "./copy-answer";

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
    is_synthetic: false,
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

const conflictLabels: ConflictCopyLabels = {
  status: "Sources give different recommendations (Unresolved)",
  sources: "Sources",
  snapshot: "Snapshot",
  synthetic: "synthetic document",
  date: "date",
  unknownDate: "unknown",
  version: "product version",
  notProvided: "not specified",
};

const conflictResult: ConflictingResult = {
  outcome: "conflicting",
  conflict_type: "different_recommendations",
  summary:
    "The values differ, but it is unclear whether they apply to the same situation.",
  comparison_rows: [
    {
      kind: "recommendation",
      label: "nproc",
      side_a: "131072",
      side_b: "1024",
    },
  ],
  refine_hint: "WAS or RHEL version",
  extra_conflicting_docs: 0,
  checked_chunks: [],
  omitted_claims: 0,
  sides: [
    {
      label: "A",
      doc_id: "swg21648497",
      snapshot_id: "techqa@0b5bbc8f2d4e6a1c",
      title: "IBM Insufficient ulimit Value Causes Native OutOfMemory",
      headings: ["DIAGNOSING THE PROBLEM"],
      chunk_id: "chunk-a",
      claim_text: "Set ulimit -u / nproc to 131072 for the WAS user on Linux.",
      code: "ulimit -u 131072",
      quote: "recommends setting the ulimit -u or nproc to a value of 131072",
      quote_start: 0,
      quote_end: 62,
      is_synthetic: false,
      doc_date: null,
      product_version: null,
      audience: "WebSphere Support",
    },
    {
      label: "B",
      doc_id: "SYN-KB-0007",
      snapshot_id: "synthetic@v1",
      title: "Runbook: WebSphere Application Server on Linux — process limits",
      headings: ["Process limits"],
      chunk_id: "chunk-b",
      claim_text: "Keep nproc at the RHEL default of 1024.",
      code: null,
      quote: "Keep nproc at the RHEL default of 1024 for the WebSphere user.",
      quote_start: 0,
      quote_end: 62,
      is_synthetic: true,
      doc_date: "2019-03",
      product_version: "WAS 8.5",
      audience: "platform team",
    },
  ],
};

describe("formatConflictForCopy", () => {
  const conflictText = formatConflictForCopy(
    conflictResult,
    snapshotId,
    conflictLabels,
  );
  const conflictLines = conflictText.split("\n");

  it("zawiera obie instrukcje z oznaczeniami [A]/[B] i doc_id oraz wcięty kod", () => {
    expect(conflictLines).toContain(
      "[A] Set ulimit -u / nproc to 131072 for the WAS user on Linux. (swg21648497)",
    );
    expect(conflictLines).toContain("    ulimit -u 131072");
    expect(conflictLines).toContain(
      "[B] Keep nproc at the RHEL default of 1024. (SYN-KB-0007)",
    );
  });

  it("zawiera sekcję źródeł z metadanymi i skróconą migawką", () => {
    expect(conflictText).toBe(
      [
        "Sources give different recommendations (Unresolved)",
        "The values differ, but it is unclear whether they apply to the same situation.",
        "",
        "[A] Set ulimit -u / nproc to 131072 for the WAS user on Linux. (swg21648497)",
        "    ulimit -u 131072",
        "[B] Keep nproc at the RHEL default of 1024. (SYN-KB-0007)",
        "",
        "Sources:",
        "[A] swg21648497 — IBM Insufficient ulimit Value Causes Native OutOfMemory (date: unknown, product version: not specified)",
        "[B] SYN-KB-0007 — Runbook: WebSphere Application Server on Linux — process limits (synthetic document, date: 2019-03, product version: WAS 8.5)",
        "Snapshot: 0b5bbc8",
        "",
      ].join("\n"),
    );
  });
});
