import {
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type Ref,
} from "react";

import { useT } from "../../i18n/context";

const MAX_QUESTION_LENGTH = 2000;
const MAX_HEIGHT_PX = 168;

export type ComposerHandle = {
  /** Wstawia tekst do pola i ustawia w nim fokus (np. „Doprecyzuj pytanie”). */
  focusWith(text: string): void;
};

type ComposerProps = {
  onSubmit: (question: string) => void;
  /** Trwa wysyłanie pytania: przycisk i Enter są wyłączone. */
  busy: boolean;
  placeholder: string;
  ref?: Ref<ComposerHandle>;
};

/** Pole pytania z podpowiedzią o zakresie (S1P). Enter wysyła, Shift+Enter daje nową linię. */
export function Composer({ onSubmit, busy, placeholder, ref }: ComposerProps) {
  const t = useT();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focusWith(text) {
      setValue(text);
      requestAnimationFrame(() => {
        const element = textareaRef.current;
        if (!element) return;
        element.focus();
        element.setSelectionRange(text.length, text.length);
      });
    },
  }));

  // Pole rośnie z treścią do limitu wysokości.
  useLayoutEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const question = value.trim();
  const canSubmit = question.length > 0 && !busy;

  function submit() {
    if (!canSubmit) return;
    onSubmit(question);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="rounded-xl border border-border px-3.5 py-2.5 pr-3 shadow-[0_2px_8px_rgba(31,32,35,.06)]">
      <textarea
        ref={textareaRef}
        aria-label={t("composer.label")}
        rows={1}
        maxLength={MAX_QUESTION_LENGTH}
        placeholder={placeholder}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        className="block h-7 w-full resize-none border-0 bg-transparent p-0 text-[15px] leading-6 outline-0 placeholder:text-[#6b7078]"
      />
      <div className="mt-2 flex items-center justify-between gap-4">
        <span className="text-xs leading-[18px] text-muted">
          {t("composer.scope")}
        </span>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={submit}
          className="inline-flex h-8 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-primary px-4 text-sm font-medium whitespace-nowrap text-white hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:brightness-100"
        >
          {t("composer.submit")}
        </button>
      </div>
    </div>
  );
}
