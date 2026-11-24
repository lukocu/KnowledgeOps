import { useLanguage, useT } from "../../i18n/context";
import type { Lang } from "../../i18n/context";

const LANGS: { value: Lang; label: "header.langPl" | "header.langEn" }[] = [
  { value: "pl", label: "header.langPl" },
  { value: "en", label: "header.langEn" },
];

export function LanguageSwitch() {
  const t = useT();
  const { lang, setLang } = useLanguage();

  return (
    <div
      role="group"
      aria-label={t("header.langGroup")}
      title={t("header.langNotice")}
      className="inline-flex gap-0.5 text-xs leading-5 font-semibold"
    >
      {LANGS.map(({ value, label }) => {
        const pressed = lang === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={pressed}
            onClick={() => setLang(value)}
            className={
              "h-[22px] cursor-pointer rounded-[5px] border-0 bg-transparent px-1.5 " +
              (pressed
                ? "font-semibold text-text underline underline-offset-[3px]"
                : "font-medium text-muted")
            }
          >
            {t(label)}
          </button>
        );
      })}
    </div>
  );
}
