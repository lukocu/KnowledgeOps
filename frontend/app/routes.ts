import {
  type RouteConfig,
  index,
  layout,
  route,
} from "@react-router/dev/routes";

export default [
  layout("routes/_layout.tsx", [
    index("routes/assistant.tsx"),
    route("odpowiedz/:id", "routes/answer.tsx"),
    route("audyt", "routes/audit-new.tsx"),
    route("audyt/:id", "routes/audit-detail.tsx"),
    route("analizy", "routes/analyses.tsx"),
  ]),
] satisfies RouteConfig;
