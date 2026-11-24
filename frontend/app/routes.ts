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
  ]),
] satisfies RouteConfig;
