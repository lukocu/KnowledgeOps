import { useId, useState } from "react";
import { Outlet } from "react-router";

import { AppHeader } from "../components/shell/AppHeader";
import { NavDrawer, NavRail } from "../components/shell/NavRail";
import { useMediaQuery, WIDE_QUERY } from "../lib/use-media-query";
import { RoleProvider } from "../session/role";

/**
 * Wspólny układ tras aplikacji (S1A/S1P/1N): nagłówek, nawigacja i obszar treści.
 * Od 768 px nawigacja to szyna, poniżej szuflada otwierana przyciskiem Menu.
 */
export default function AppLayout() {
  const wide = useMediaQuery(WIDE_QUERY);
  const drawerId = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const [prevWide, setPrevWide] = useState(wide);

  // Przejście do szerokiego okna zamyka szufladę, żeby nie wróciła sama po zwężeniu.
  if (wide !== prevWide) {
    setPrevWide(wide);
    if (wide) setMenuOpen(false);
  }

  return (
    <RoleProvider>
      <div className="flex h-screen flex-col overflow-hidden bg-white text-text">
        <AppHeader
          onOpenMenu={() => setMenuOpen(true)}
          menuOpen={menuOpen}
          menuId={drawerId}
        />
        <div className="flex min-h-0 flex-1">
          {wide ? (
            <NavRail />
          ) : (
            <NavDrawer
              id={drawerId}
              open={menuOpen}
              onClose={() => setMenuOpen(false)}
            />
          )}
          <main className="relative flex min-w-0 flex-1 flex-col overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </RoleProvider>
  );
}
