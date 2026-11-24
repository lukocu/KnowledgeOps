import { Outlet } from "react-router";

import { AppHeader } from "../components/shell/AppHeader";
import { NavRail } from "../components/shell/NavRail";
import { RoleProvider } from "../session/role";

/** Wspólny układ tras aplikacji (S1A/S1P): nagłówek, nawigacja i obszar treści. */
export default function AppLayout() {
  return (
    <RoleProvider>
      <div className="flex h-screen flex-col overflow-hidden bg-white text-text">
        <AppHeader />
        <div className="flex min-h-0 flex-1">
          <NavRail />
          <main className="relative flex min-w-0 flex-1 flex-col overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </RoleProvider>
  );
}
