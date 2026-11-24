import { useRef } from "react";

import { AssistantFrame } from "../components/assistant/AssistantFrame";
import {
  Composer,
  type ComposerHandle,
} from "../components/assistant/Composer";
import { ErrorState } from "../components/assistant/ErrorState";
import { ProgressCard } from "../components/assistant/ProgressCard";
import { QuestionBubble } from "../components/assistant/QuestionBubble";
import { useAsk } from "../components/assistant/useAsk";
import { useT } from "../i18n/context";
import { deriveSteps } from "../lib/stages";

export function meta() {
  return [{ title: "KnowledgeOps" }];
}

/** Trasa `/`: nowe pytanie (1P). Po wyniku przechodzi na `/odpowiedz/:id`. */
export default function Assistant() {
  const t = useT();
  const { state, ask } = useAsk();
  const composerRef = useRef<ComposerHandle>(null);

  let thread;
  if (state.status === "asking") {
    thread = (
      <>
        <QuestionBubble question={state.question} />
        <ProgressCard steps={deriveSteps(state.stages)} />
      </>
    );
  } else if (state.status === "failed") {
    const { question, error } = state;
    thread = (
      <>
        <QuestionBubble question={question} />
        <ErrorState code={error.code} onRetry={() => ask(question)} />
      </>
    );
  } else {
    thread = (
      <>
        <h1 className="m-0 text-base font-semibold">{t("assistant.title")}</h1>
        <p className="mt-2 max-w-[640px] text-[15px] leading-6 text-muted">
          {t("assistant.intro")}
        </p>
      </>
    );
  }

  return (
    <AssistantFrame
      thread={thread}
      composer={
        <Composer
          ref={composerRef}
          onSubmit={ask}
          busy={state.status === "asking"}
          placeholder={t("composer.placeholder")}
        />
      }
    />
  );
}
