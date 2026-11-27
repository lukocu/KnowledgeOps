import { AnalysesListView } from "../components/audit/AnalysesListView";

export function meta() {
  return [{ title: "KnowledgeOps" }];
}

/** Trasa `/analizy`: ekran 5 („Analizy i decyzje”). */
export default function AnalysesRoute() {
  return <AnalysesListView />;
}
