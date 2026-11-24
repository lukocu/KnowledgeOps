/** localStorage może rzucać (tryb prywatny, zablokowane dane) albo nie istnieć (prerender). */
export function readStorage(key: string): string | null {
  try {
    return typeof window === "undefined"
      ? null
      : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // Wybór działa w tej karcie nawet bez trwałego zapisu.
  }
}
