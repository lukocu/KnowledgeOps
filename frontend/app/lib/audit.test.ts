import { describe, expect, it } from "vitest";

import type { Translate } from "../i18n/context";
import { en } from "../i18n/en";
import { pl } from "../i18n/pl";
import {
  buildNoteSegments,
  canSubmitDecision,
  claimTag,
  countAwaitingDecision,
  countUniqueCheckedDocs,
  DECISION_CATEGORIES,
  DECISION_CATEGORY_LABEL,
  DECISION_STATUS_LABEL,
  deriveAuditSteps,
  formatAuditTimestamp,
  formatClaimBreakdown,
  formatCompactTimestamp,
  formatSummaryLine,
  hasActiveListFilters,
  hasActiveSearchOrStatusFilters,
  hasSyntheticScope,
  HISTORY_EVENT_LABEL,
  isDecisionUnchanged,
  isEditableTarget,
  MAX_JUSTIFICATION_LENGTH,
} from "./audit";

function makeTranslator(dict: typeof pl | typeof en): Translate {
  return (key, vars) => {
    let text = dict[key];
    if (vars) {
      for (const [name, replacement] of Object.entries(vars)) {
        text = text.replaceAll(`{${name}}`, String(replacement));
      }
    }
    return text;
  };
}

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

describe("decyzje redaktora i historia", () => {
  it("utrzymuje stałą kolejność 4 kategorii decyzji z PRD i mapuje etykiety i18n", () => {
    expect(DECISION_CATEGORIES).toEqual([
      "agree_with_system",
      "request_source_or_verify",
      "consider_doc_update",
      "system_verdict_wrong",
    ]);
    for (const category of DECISION_CATEGORIES) {
      expect(DECISION_CATEGORY_LABEL[category]).toBeTruthy();
    }
    expect(Object.keys(DECISION_STATUS_LABEL).sort()).toEqual([
      "in_progress",
      "not_applicable",
      "pending",
      "saved",
    ]);
    expect(Object.keys(HISTORY_EVENT_LABEL).sort()).toEqual([
      "audit_created",
      "decision_saved",
      "decision_updated",
      "evaluation_completed",
      "evaluation_failed",
    ]);
  });

  it("blokuje zapis przy braku wybranej kategorii lub pustym uzasadnieniu (w tym samych spacjach)", () => {
    expect(canSubmitDecision(null, "Uzasadnienie", null, false)).toBe(false);
    expect(canSubmitDecision("agree_with_system", "", null, false)).toBe(false);
    expect(
      canSubmitDecision("agree_with_system", "   \n\t  ", null, false),
    ).toBe(false);
    expect(
      canSubmitDecision(
        "agree_with_system",
        "a".repeat(MAX_JUSTIFICATION_LENGTH + 1),
        null,
        false,
      ),
    ).toBe(false);
    expect(
      canSubmitDecision("agree_with_system", "Potwierdzone.", null, true),
    ).toBe(false);
    expect(
      canSubmitDecision("agree_with_system", "Potwierdzone.", null, false),
    ).toBe(true);
  });

  it("wykrywa niezmienioną decyzję przy edycji i odblokowuje zapis po zmianie kategorii lub uzasadnienia", () => {
    const saved = {
      decision: "request_source_or_verify" as const,
      justification: "Brak potwierdzenia w dokumentacji.",
    };

    expect(
      isDecisionUnchanged(
        "request_source_or_verify",
        "  Brak potwierdzenia w dokumentacji.  ",
        saved,
      ),
    ).toBe(true);
    expect(
      canSubmitDecision(
        "request_source_or_verify",
        "  Brak potwierdzenia w dokumentacji.  ",
        saved,
        false,
      ),
    ).toBe(false);

    expect(
      canSubmitDecision(
        "consider_doc_update",
        "Brak potwierdzenia w dokumentacji.",
        saved,
        false,
      ),
    ).toBe(true);
    expect(
      canSubmitDecision(
        "request_source_or_verify",
        "Zweryfikowano z zespołem produktu.",
        saved,
        false,
      ),
    ).toBe(true);
  });

  it("rozpoznaje cele edytowalne (INPUT, TEXTAREA, SELECT, contentEditable)", () => {
    expect(isEditableTarget(null)).toBe(false);
    expect(isEditableTarget({ tagName: "DIV" } as unknown as EventTarget)).toBe(
      false,
    );
    expect(
      isEditableTarget({ tagName: "BUTTON" } as unknown as EventTarget),
    ).toBe(false);
    expect(
      isEditableTarget({ tagName: "INPUT" } as unknown as EventTarget),
    ).toBe(true);
    expect(
      isEditableTarget({ tagName: "textarea" } as unknown as EventTarget),
    ).toBe(true);
    expect(
      isEditableTarget({ tagName: "SELECT" } as unknown as EventTarget),
    ).toBe(true);
    expect(
      isEditableTarget({
        tagName: "DIV",
        isContentEditable: true,
      } as unknown as EventTarget),
    ).toBe(true);
  });

  it("formatuje poprawny znacznik czasu ISO i zwraca surowy ciąg dla niepoprawnej daty", () => {
    expect(formatAuditTimestamp("not-a-date", "pl")).toBe("not-a-date");
    const formattedPl = formatAuditTimestamp("2026-11-27T12:30:00Z", "pl");
    const formattedEn = formatAuditTimestamp("2026-11-27T12:30:00Z", "en");
    expect(formattedPl.length).toBeGreaterThan(0);
    expect(formattedEn.length).toBeGreaterThan(0);
  });
});

describe("lista analiz (/analizy)", () => {
  const tPl = makeTranslator(pl);
  const tEn = makeTranslator(en);

  it("formatClaimBreakdown obsługuje wszystkie warianty werdyktów i 0 tez (PL i EN)", () => {
    expect(
      formatClaimBreakdown(
        {
          claims_supported: 0,
          claims_contradicted: 0,
          claims_insufficient: 0,
        },
        tPl,
        "pl",
      ),
    ).toBe("");

    expect(
      formatClaimBreakdown(
        {
          claims_supported: 2,
          claims_contradicted: 0,
          claims_insufficient: 0,
        },
        tPl,
        "pl",
      ),
    ).toBe("2 poparte");

    expect(
      formatClaimBreakdown(
        {
          claims_supported: 1,
          claims_contradicted: 0,
          claims_insufficient: 1,
        },
        tPl,
        "pl",
      ),
    ).toBe("1 poparta · 1 bez wystarczających dowodów");

    expect(
      formatClaimBreakdown(
        {
          claims_supported: 5,
          claims_contradicted: 1,
          claims_insufficient: 2,
        },
        tPl,
        "pl",
      ),
    ).toBe("1 sprzeczna · 5 popartych · 2 bez wystarczających dowodów");

    expect(
      formatClaimBreakdown(
        {
          claims_supported: 1,
          claims_contradicted: 2,
          claims_insufficient: 1,
        },
        tEn,
        "en",
      ),
    ).toBe("2 contradicted · 1 supported · 1 insufficient evidence");
  });

  it("formatCompactTimestamp formatuje datę w układzie DD.MM HH:MM (PL) i DD/MM HH:MM (EN)", () => {
    expect(formatCompactTimestamp("not-a-date", "pl")).toBe("not-a-date");
    expect(formatCompactTimestamp("2026-11-22T10:22:00", "pl")).toBe(
      "22.11 10:22",
    );
    expect(formatCompactTimestamp("2026-03-05T08:04:00", "en")).toBe(
      "05/03 08:04",
    );
  });

  it("hasActiveListFilters rozróżnia stan pusty filtrów od aktywnego filtra", () => {
    expect(hasActiveListFilters({})).toBe(false);
    expect(
      hasActiveListFilters({
        q: "   ",
        decision_status: null,
        note_verdict: null,
        source: "all",
      }),
    ).toBe(false);

    expect(hasActiveListFilters({ q: "SIM-P04" })).toBe(true);
    expect(hasActiveListFilters({ decision_status: "pending" })).toBe(true);
    expect(hasActiveListFilters({ note_verdict: "contradiction" })).toBe(true);
    expect(hasActiveListFilters({ source: "demo" })).toBe(true);
    expect(hasActiveListFilters({ source: "session" })).toBe(true);

    expect(hasActiveSearchOrStatusFilters({ source: "session" })).toBe(false);
    expect(hasActiveSearchOrStatusFilters({ q: "streams" })).toBe(true);
  });

  it("zlicza analizy oczekujące i formatuje pasek podsumowania liczbowego", () => {
    const summary = {
      demo_count: 4,
      session_count: 2,
      pending_count: 2,
      in_progress_count: 1,
      saved_count: 3,
      next_pending_audit_id: "a1",
      next_pending_case_ref: "SIM-P08",
    };

    expect(countAwaitingDecision(summary)).toBe(3);
    expect(formatSummaryLine(summary, tPl, "pl")).toBe(
      "4 przykłady · 2 Twoje (ta sesja) · 2 czekają · 1 w toku · 3 zapisane",
    );
    expect(formatSummaryLine(summary, tEn, "en")).toBe(
      "4 examples · 2 yours (this session) · 2 awaiting · 1 in progress · 3 saved",
    );
  });
});
