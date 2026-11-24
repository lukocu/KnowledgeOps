import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const client = createClient<paths>({
  baseUrl: "/",
  credentials: "same-origin",
});

type HealthPath = paths["/api/health"]["get"]["responses"];

/** Ta sama struktura dla 200 i 503 (baza niedostępna = `degraded`). */
export type HealthResponse = HealthPath[200]["content"]["application/json"];

export async function getHealth(): Promise<HealthResponse> {
  const { data, error, response } = await client.GET("/api/health");
  // Treść ma schemat HealthResponse tylko dla 200 i 503; inne błędy (np. 502 z proxy) odrzucamy.
  if (response.status !== 200 && response.status !== 503) {
    throw new Error(`Nieoczekiwana odpowiedź /api/health: ${response.status}`);
  }
  const body = data ?? error;
  if (!body) {
    throw new Error("Pusta odpowiedź /api/health");
  }
  return body;
}
