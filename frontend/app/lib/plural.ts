export type PluralForm = "One" | "Few" | "Many";

/** Forma liczby: PL (1 / 2–4 poza 12–14 / reszta) i EN (1 / reszta, „Few” nieużywane). */
export function pluralForm(lang: string, n: number): PluralForm {
  if (n === 1) return "One";
  if (lang === "pl") {
    const lastTwo = n % 100;
    const last = n % 10;
    if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) {
      return "Few";
    }
  }
  return "Many";
}
