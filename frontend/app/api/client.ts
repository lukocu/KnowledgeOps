import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const client = createClient<paths>({ baseUrl: "/" });

type HealthPath = paths["/api/health"]["get"]["responses"];

/** Ta sama struktura dla 200 i 503 (baza niedostępna = `degraded`). */
export type HealthResponse = HealthPath[200]["content"]["application/json"];

export async function getHealth(): Promise<HealthResponse> {
  const { data, error } = await client.GET("/api/health");
  const body = data ?? error;
  if (!body) {
    throw new Error("Pusta odpowiedź /api/health");
  }
  return body;
}
