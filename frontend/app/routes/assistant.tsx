import { useT } from "../i18n/context";

export function meta() {
  return [{ title: "KnowledgeOps" }];
}

/** Placeholder trasy „Asystent”. Ekrany 1P/1A/1C dochodzą w Fazie 5. */
export default function Assistant() {
  const t = useT();

  return (
    <div className="px-10 pt-7">
      <h1 className="m-0 text-base font-semibold">
        {t("assistant.placeholderTitle")}
      </h1>
      <p className="mt-2 max-w-[640px] text-[15px] leading-6 text-muted">
        {t("assistant.placeholderBody")}
      </p>
    </div>
  );
}
