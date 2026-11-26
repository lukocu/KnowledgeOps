import { createSseParser } from "../lib/sse";
import { client } from "./client";
import type { components } from "./schema";

export type StageEvent = components["schemas"]["StageEvent"];
export type ResultEvent = components["schemas"]["ResultEvent"];
export type ErrorEvent = components["schemas"]["ErrorEvent"];
export type AnswerRecord = components["schemas"]["AnswerRecord"];
export type AnsweredResult = components["schemas"]["AnsweredResult"];
export type AbstainedResult = components["schemas"]["AbstainedResult"];
export type ConflictingResult = components["schemas"]["ConflictingResult"];
export type ConflictSide = components["schemas"]["ConflictSide"];
export type ConflictType = ConflictingResult["conflict_type"];
export type ConflictComparisonRow =
  components["schemas"]["ConflictComparisonRow"];
export type Citation = components["schemas"]["Citation"];
export type CheckedChunk = components["schemas"]["CheckedChunk"];
export type EvidenceWindow = components["schemas"]["EvidenceWindow"];
export type DocumentText = components["schemas"]["DocumentText"];

/** Odpowiedź HTTP spoza 2xx (np. 404 dla odpowiedzi z innej sesji). */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`Odpowiedź API: ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

export type AskOptions = {
  signal?: AbortSignal;
  /** Wywoływane dla każdego zdarzenia `stage`, w kolejności odbioru. */
  onStage?: (event: StageEvent) => void;
};

function failure(message: string): ErrorEvent {
  return { answer_id: null, code: "internal", message };
}

/**
 * Wysyła pytanie (`POST /api/answers`) i czyta strumień SSE przez `fetch`
 * (`EventSource` obsługuje tylko GET). Zwraca zdarzenie końcowe: `result` albo `error`.
 * Błędy sieci i HTTP są zwracane jako `ErrorEvent`; przerwanie przez `signal` rzuca `AbortError`.
 */
export async function askQuestion(
  question: string,
  { signal, onStage }: AskOptions = {},
): Promise<ResultEvent | ErrorEvent> {
  const body: components["schemas"]["AnswerRequest"] = { question };
  try {
    const response = await fetch("/api/answers", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      credentials: "same-origin",
      signal,
    });
    if (!response.ok || !response.body) {
      return failure(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const parser = createSseParser();
    let terminal: ResultEvent | ErrorEvent | null = null;

    for (;;) {
      const { done, value } = await reader.read();
      const text = decoder.decode(value, { stream: !done });
      for (const message of parser.push(text)) {
        const payload = JSON.parse(message.data) as unknown;
        if (message.event === "stage") {
          onStage?.(payload as StageEvent);
        } else if (message.event === "result") {
          terminal = payload as ResultEvent;
        } else if (message.event === "error") {
          terminal = payload as ErrorEvent;
        }
      }
      if (terminal || done) break;
    }
    void reader.cancel().catch(() => undefined);
    return terminal ?? failure("Strumień zakończył się bez wyniku");
  } catch (error) {
    if (signal?.aborted) throw error;
    return failure(error instanceof Error ? error.message : "Błąd połączenia");
  }
}

export async function getAnswer(
  id: string,
  signal?: AbortSignal,
): Promise<AnswerRecord> {
  const { data, response } = await client.GET("/api/answers/{answer_id}", {
    params: { path: { answer_id: id } },
    credentials: "same-origin",
    signal,
  });
  if (!data) throw new ApiError(response.status);
  // openapi-fetch poszerza krotkę `sides: [ConflictSide, ConflictSide]` do tablicy.
  return data as AnswerRecord;
}

export async function getEvidence(
  chunkId: string,
  before: number,
  after: number,
  signal?: AbortSignal,
): Promise<EvidenceWindow> {
  const { data, response } = await client.GET("/api/evidence", {
    params: { query: { chunk_id: chunkId, before, after } },
    credentials: "same-origin",
    signal,
  });
  if (!data) throw new ApiError(response.status);
  return data;
}

export async function getDocument(
  snapshotId: string,
  docId: string,
  signal?: AbortSignal,
): Promise<DocumentText> {
  const { data, response } = await client.GET("/api/documents", {
    params: { query: { snapshot_id: snapshotId, doc_id: docId } },
    credentials: "same-origin",
    signal,
  });
  if (!data) throw new ApiError(response.status);
  return data;
}
