import type { ReactNode } from "react";

/**
 * Wspólny układ ekranów asystenta (S1P/S1A/S1C): przewijana treść, kompozytor
 * przypięty u dołu i opcjonalny panel boczny po prawej.
 */
export function AssistantFrame({
  thread,
  composer,
  panel,
}: {
  thread: ReactNode;
  composer: ReactNode;
  panel?: ReactNode;
}) {
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-4 pb-6 md:px-6 md:pt-7 xl:px-10">
          {thread}
        </div>
        <div className="flex-none px-4 pb-4 md:px-6 xl:px-10">{composer}</div>
      </div>
      {panel}
    </div>
  );
}
