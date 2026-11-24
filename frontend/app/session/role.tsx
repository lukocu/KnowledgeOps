import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { readStorage, writeStorage } from "../lib/safe-storage";

export type Role = "consultant" | "editor";

const STORAGE_KEY = "kops.role";

type RoleValue = { role: Role; setRole: (role: Role) => void };

const RoleContext = createContext<RoleValue | null>(null);

function readInitialRole(): Role {
  return readStorage(STORAGE_KEY) === "editor" ? "editor" : "consultant";
}

/** Rola jest tylko etykietą interfejsu (FR-011): nie zmienia uprawnień ani danych. */
export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(readInitialRole);

  const setRole = useCallback((next: Role) => {
    setRoleState(next);
    writeStorage(STORAGE_KEY, next);
  }, []);

  const value = useMemo(() => ({ role, setRole }), [role, setRole]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleValue {
  const value = useContext(RoleContext);
  if (!value) {
    throw new Error("RoleProvider nie otacza tego komponentu");
  }
  return value;
}
