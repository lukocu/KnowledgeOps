import { useId } from "react";

import { useT } from "../../i18n/context";
import { useRole, type Role } from "../../session/role";

const ROLES: {
  value: Role;
  label: "header.roleConsultant" | "header.roleEditor";
}[] = [
  { value: "consultant", label: "header.roleConsultant" },
  { value: "editor", label: "header.roleEditor" },
];

export function RoleSwitch() {
  const t = useT();
  const { role, setRole } = useRole();
  const noticeId = useId();

  return (
    <>
      <div
        role="group"
        aria-label={t("header.roleGroup")}
        aria-describedby={noticeId}
        title={t("header.roleNotice")}
        className="inline-flex gap-0.5 rounded-lg bg-surface p-0.5"
      >
        {ROLES.map(({ value, label }) => {
          const pressed = role === value;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={pressed}
              onClick={() => setRole(value)}
              className={
                "h-[26px] cursor-pointer rounded-md border-0 px-3 text-[13px] " +
                (pressed
                  ? "bg-white font-semibold text-text shadow-[0_1px_2px_rgba(31,32,35,.14)]"
                  : "bg-transparent font-medium text-muted")
              }
            >
              {t(label)}
            </button>
          );
        })}
      </div>
      {/* Poniżej 768 px (1N) notka jest tylko dla czytników ekranu; treść zostaje też w title. */}
      <span
        id={noticeId}
        className="sr-only text-xs whitespace-nowrap text-muted md:not-sr-only"
      >
        {t("header.roleNoticeShort")}
      </span>
    </>
  );
}
