import { ApiError } from "./answers";
import { client } from "./client";
import type { components } from "./schema";

export type CreateAuditRequest = components["schemas"]["CreateAuditRequest"];
export type CreateAuditResponse = components["schemas"]["CreateAuditResponse"];
export type AuditDetailResponse = components["schemas"]["AuditDetailResponse"];
export type AuditClaimResponse = components["schemas"]["AuditClaimResponse"];
export type CaseContext = components["schemas"]["CaseContext"];
export type ClaimEvidence = components["schemas"]["ClaimEvidence"];
export type CheckedDoc = components["schemas"]["CheckedDoc"];
export type AuditStatus = AuditDetailResponse["status"];
export type AuditStage = AuditDetailResponse["stage"];
export type ClaimVerdict = AuditClaimResponse["verdict"];
export type NoteVerdict = NonNullable<AuditDetailResponse["note_verdict"]>;

/** Zleca audyt notatki ze sprawy (`POST /api/audits` → `202 Accepted`). */
export async function createAudit(
  body: CreateAuditRequest,
  signal?: AbortSignal,
): Promise<CreateAuditResponse> {
  const { data, response } = await client.POST("/api/audits", {
    body,
    credentials: "same-origin",
    signal,
  });
  if (!data) throw new ApiError(response.status);
  return data;
}

/** Pobiera bieżący stan lub wynik audytu (`GET /api/audits/{audit_id}`). */
export async function fetchAudit(
  auditId: string,
  signal?: AbortSignal,
): Promise<AuditDetailResponse> {
  const { data, response } = await client.GET("/api/audits/{audit_id}", {
    params: { path: { audit_id: auditId } },
    credentials: "same-origin",
    signal,
  });
  if (!data) throw new ApiError(response.status);
  return data;
}
