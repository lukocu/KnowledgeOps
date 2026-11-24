export type Range = readonly [start: number, end: number];
export type Segment = { text: string; marked: boolean };

/**
 * Dzieli `text` na odcinki zaznaczone i niezaznaczone według zakresów `[start, end)`.
 * Zakresy są przycinane do tekstu, sortowane i scalane, gdy się nakładają.
 */
export function splitSegments(
  text: string,
  ranges: readonly Range[],
): Segment[] {
  const clamped = ranges
    .map(([start, end]) => [
      Math.max(0, Math.min(start, text.length)),
      Math.max(0, Math.min(end, text.length)),
    ])
    .filter(([start, end]) => end > start)
    .sort((a, b) => a[0] - b[0]);

  const merged: [number, number][] = [];
  for (const [start, end] of clamped) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }

  const segments: Segment[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), marked: false });
    }
    segments.push({ text: text.slice(start, end), marked: true });
    cursor = end;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), marked: false });
  }
  return segments;
}
