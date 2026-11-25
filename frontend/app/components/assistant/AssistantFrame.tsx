import type { ReactNode } from "react";

import { PanelFrame, type PanelVariant } from "./PanelFrame";

/**
 * Wspólny układ ekranów asystenta (S1P/S1A/S1C): przewijana treść, kompozytor
 * przypięty u dołu i opcjonalny panel boczny po prawej (w wąskim oknie arkusz).
 */
export function AssistantFrame({
  thread,
  composer,
  panel,
  panelFrame,
}: {
  thread: ReactNode;
  composer: ReactNode;
  panel?: ReactNode;
  /** Obudowa panelu; renderowana tu raz, by przełączanie treści panelu jej nie przemontowywało. */
  panelFrame?: {
    label: string;
    variant: PanelVariant;
    onDismiss: () => void;
  };
}) {
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-[16px] pt-[16px] pb-6 md:px-6 md:pt-7 xl:px-10">
          {thread}
        </div>
        <div className="flex-none px-[16px] pb-4 md:px-6 xl:px-10">
          {composer}
        </div>
      </div>
      {panel && panelFrame ? (
        <PanelFrame
          label={panelFrame.label}
          variant={panelFrame.variant}
          onDismiss={panelFrame.onDismiss}
        >
          {panel}
        </PanelFrame>
      ) : (
        panel
      )}
    </div>
  );
}
