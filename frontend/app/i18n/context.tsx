import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { readStorage, writeStorage } from "../lib/safe-storage";
import { en } from "./en";
import { pl, type TranslationKey } from "./pl";

export type Lang = "pl" | "en";

const STORAGE_KEY = "kops.lang";
const DICTIONARIES: Record<Lang, Record<TranslationKey, string>> = { pl, en };

export type Translate = (
  key: TranslationKey,
  vars?: Record<string, string | number>,
) => string;

type LanguageValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Translate;
};

const LanguageContext = createContext<LanguageValue | null>(null);

function readInitialLang(): Lang {
  return readStorage(STORAGE_KEY) === "en" ? "en" : "pl";
}

/**
 * Stan startowy czytany synchronicznie z localStorage (SPA, brak SSR), więc pierwszy
 * render aplikacji od razu ma właściwy język, bez mignięcia domyślnym.
 */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    writeStorage(STORAGE_KEY, next);
  }, []);

  const value = useMemo<LanguageValue>(() => {
    const dictionary = DICTIONARIES[lang];
    const t: Translate = (key, vars) => {
      let text = dictionary[key];
      if (vars) {
        for (const [name, replacement] of Object.entries(vars)) {
          text = text.replaceAll(`{${name}}`, String(replacement));
        }
      }
      return text;
    };
    return { lang, setLang, t };
  }, [lang, setLang]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

function useLanguageValue(): LanguageValue {
  const value = useContext(LanguageContext);
  if (!value) {
    throw new Error("LanguageProvider nie otacza tego komponentu");
  }
  return value;
}

export function useT(): Translate {
  return useLanguageValue().t;
}

export function useLanguage(): Pick<LanguageValue, "lang" | "setLang"> {
  const { lang, setLang } = useLanguageValue();
  return { lang, setLang };
}
