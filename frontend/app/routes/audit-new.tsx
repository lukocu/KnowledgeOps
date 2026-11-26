import { useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { ApiError } from "../api/answers";
import { createAudit } from "../api/audits";
import {
  AuditFormView,
  AuditHowItWorksAside,
  type AuditFormValues,
} from "../components/audit/AuditFormView";
import { useT } from "../i18n/context";
import { MAX_AUDIT_TEXT_LENGTH, MAX_CASE_REF_LENGTH } from "../lib/audit";

export function meta() {
  return [{ title: "KnowledgeOps" }];
}

const EMPTY_VALUES: AuditFormValues = {
  caseRef: "",
  caseDescription: "",
  resolutionNote: "",
};

function readInitialValues(state: unknown): AuditFormValues {
  if (!state || typeof state !== "object") return EMPTY_VALUES;
  const candidate = state as Partial<AuditFormValues>;
  return {
    caseRef: typeof candidate.caseRef === "string" ? candidate.caseRef : "",
    caseDescription:
      typeof candidate.caseDescription === "string"
        ? candidate.caseDescription
        : "",
    resolutionNote:
      typeof candidate.resolutionNote === "string"
        ? candidate.resolutionNote
        : "",
  };
}

/** Trasa `/audyt` (ekran 2): ręczne przekazanie rozwiązanej sprawy do audytu. */
export default function AuditNewRoute() {
  const t = useT();
  const navigate = useNavigate();
  const location = useLocation();
  const [values, setValues] = useState<AuditFormValues>(() =>
    readInitialValues(location.state),
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function handleChange(patch: Partial<AuditFormValues>) {
    setValues((prev) => ({ ...prev, ...patch }));
    if (errorMessage) setErrorMessage(null);
  }

  function handleClear() {
    setValues(EMPTY_VALUES);
    setErrorMessage(null);
  }

  async function submitAudit() {
    const caseRef = values.caseRef.trim();
    const caseDescription = values.caseDescription.trim();
    const resolutionNote = values.resolutionNote.trim();

    if (!caseDescription || !resolutionNote) {
      setErrorMessage(t("audit.form.errorRequired"));
      return;
    }
    if (
      caseDescription.length > MAX_AUDIT_TEXT_LENGTH ||
      resolutionNote.length > MAX_AUDIT_TEXT_LENGTH
    ) {
      setErrorMessage(
        t("audit.form.errorTooLong", { max: MAX_AUDIT_TEXT_LENGTH }),
      );
      return;
    }
    if (caseRef.length > MAX_CASE_REF_LENGTH) {
      setErrorMessage(
        t("audit.form.errorTooLong", { max: MAX_CASE_REF_LENGTH }),
      );
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    try {
      const created = await createAudit({
        case_ref: caseRef || null,
        case_description: caseDescription,
        resolution_note: resolutionNote,
      });
      void navigate(`/audyt/${encodeURIComponent(created.audit_id)}`);
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 503) {
        setErrorMessage(t("audit.form.errorUnavailable"));
      } else {
        setErrorMessage(t("audit.form.errorGeneric"));
      }
      setSubmitting(false);
    }
  }

  return (
    <AuditFormView
      values={values}
      mode={submitting ? "submitting" : "editable"}
      errorMessage={errorMessage}
      onChange={handleChange}
      onSubmit={() => {
        void submitAudit();
      }}
      onClear={handleClear}
      aside={<AuditHowItWorksAside />}
    />
  );
}
