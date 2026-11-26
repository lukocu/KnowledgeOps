import { describe, expect, it } from "vitest";

import {
  buildNoteSegments,
  claimTag,
  countUniqueCheckedDocs,
  deriveAuditSteps,
  hasSyntheticScope,
} from "./audit";

describe("buildNoteSegments", () => {
  it("zwraca pustą listę dla pustej notatki", () => {
    expect(buildNoteSegments("", [])).toEqual([]);
  });

  it("zwraca pojedynczy segment tekstu, gdy brak zakotwiczonych tez", () => {
    const note = "Restart the service and verify logs.";
    expect(
      buildNoteSegments(note, [
        {
          claim_id: "c1",
          claim_index: 0,
          verdict: "insufficient",
          source_start: null,
          source_end: null,
        },
      ]),
    ).toEqual([{ kind: "text", text: note }]);
  });

  it("dzieli notatkę na segmenty tekstu i zakotwiczonych tez w kolejności offsetów", () => {
    const note = "Set variables with streamtool. Restart OS twice.";
    const segments = buildNoteSegments(note, [
      {
        claim_id: "c2",
        claim_index: 1,
        verdict: "insufficient",
        source_start: 31,
        source_end: 48,
      },
      {
        claim_id: "c1",
        claim_index: 0,
        verdict: "supported",
        source_start: 0,
        source_end: 30,
      },
    ]);

    expect(segments).toEqual([
      {
        kind: "claim",
        claimId: "c1",
        claimIndex: 0,
        verdict: "supported",
        text: "Set variables with streamtool.",
      },
      { kind: "text", text: " " },
      {
        kind: "claim",
        claimId: "c2",
        claimIndex: 1,
        verdict: "insufficient",
        text: "Restart OS twice.",
      },
    ]);
  });

  it("pomija nakładające się zakresy i przycina offsety spoza długości tekstu", () => {
    const note = "Alpha beta gamma.";
    const segments = buildNoteSegments(note, [
      {
        claim_id: "c1",
        claim_index: 0,
        verdict: "supported",
        source_start: -5,
        source_end: 10,
      },
      {
        claim_id: "c2",
        claim_index: 1,
        verdict: "contradicted",
        source_start: 6,
        source_end: 16,
      },
      {
        claim_id: "c3",
        claim_index: 2,
        verdict: "insufficient",
        source_start: 11,
        source_end: 99,
      },
    ]);

    expect(segments).toEqual([
      {
        kind: "claim",
        claimId: "c1",
        claimIndex: 0,
        verdict: "supported",
        text: "Alpha beta",
      },
      { kind: "text", text: " " },
      {
        kind: "claim",
        claimId: "c3",
        claimIndex: 2,
        verdict: "insufficient",
        text: "gamma.",
      },
    ]);
  });
});

describe("deriveAuditSteps", () => {
  it("mapuje kolejne etapy analizy na statusy kroków", () => {
    expect(deriveAuditSteps("queued", "queued")).toEqual([
      { id: "extract", status: "active" },
      { id: "retrieve", status: "pending" },
      { id: "verdict", status: "pending" },
    ]);

    expect(deriveAuditSteps("retrieving", "running")).toEqual([
      { id: "extract", status: "done" },
      { id: "retrieve", status: "active" },
      { id: "verdict", status: "pending" },
    ]);

    expect(deriveAuditSteps("verifying", "running")).toEqual([
      { id: "extract", status: "done" },
      { id: "retrieve", status: "done" },
      { id: "verdict", status: "active" },
    ]);

    expect(deriveAuditSteps("completed", "completed")).toEqual([
      { id: "extract", status: "done" },
      { id: "retrieve", status: "done" },
      { id: "verdict", status: "done" },
    ]);
  });
});

describe("pomocniki audytu", () => {
  it("formatuje etykietę tezy od T1", () => {
    expect(claimTag(0)).toBe("T1");
    expect(claimTag(2)).toBe("T3");
  });

  it("wykrywa nakładkę synthetic@v1 po fladze lub chunk_set_ids", () => {
    expect(
      hasSyntheticScope({ include_synthetic: true, chunk_set_ids: [] }),
    ).toBe(true);
    expect(
      hasSyntheticScope({
        include_synthetic: false,
        chunk_set_ids: [
          "techqa@0b5bbc8/sections-v1",
          "synthetic@v1/sections-v1",
        ],
      }),
    ).toBe(true);
    expect(
      hasSyntheticScope({
        include_synthetic: false,
        chunk_set_ids: ["techqa@0b5bbc8/sections-v1"],
      }),
    ).toBe(false);
  });

  it("zlicza unikalne dokumenty sprawdzone we wszystkich tezach", () => {
    expect(
      countUniqueCheckedDocs([
        {
          checked_docs: [
            {
              chunk_id: "c1",
              chunk_set_id: "cs1",
              document_id: "doc-1",
              document_title: "Doc 1",
              is_synthetic: false,
              score: 1,
              snapshot_id: "techqa@1",
              source_doc_id: "doc-1",
            },
            {
              chunk_id: "c2",
              chunk_set_id: "cs1",
              document_id: "doc-2",
              document_title: "Doc 2",
              is_synthetic: false,
              score: 0.8,
              snapshot_id: "techqa@1",
              source_doc_id: "doc-2",
            },
          ],
        },
        {
          checked_docs: [
            {
              chunk_id: "c3",
              chunk_set_id: "cs1",
              document_id: "doc-1",
              document_title: "Doc 1",
              is_synthetic: false,
              score: 0.9,
              snapshot_id: "techqa@1",
              source_doc_id: "doc-1",
            },
          ],
        },
      ]),
    ).toBe(2);
  });
});
