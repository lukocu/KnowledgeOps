/** Jedno zdarzenie SSE: nazwa (`event:`) i połączone linie `data:`. */
export type SseMessage = { event: string; data: string };

export type SseParser = {
  /** Przyjmuje kolejną porcję tekstu i zwraca zdarzenia, które właśnie się domknęły. */
  push(chunk: string): SseMessage[];
};

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // komentarz / keepalive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length > 0 ? { event, data: data.join("\n") } : null;
}

/**
 * Czysty parser strumienia `text/event-stream`. Zdarzenia mogą być rozcięte w dowolnym
 * miejscu między porcjami (także w środku `\r\n`); obsługuje `\n`, `\r\n` i `\r`.
 */
export function createSseParser(): SseParser {
  let buffer = "";

  return {
    push(chunk) {
      buffer += chunk;
      // Końcowe `\r` może być połową `\r\n`: zostawiamy je do następnej porcji.
      const held = buffer.endsWith("\r") ? "\r" : "";
      const ready = buffer
        .slice(0, buffer.length - held.length)
        .replace(/\r\n|\r/g, "\n");

      const blocks = ready.split("\n\n");
      const rest = blocks.pop() ?? "";
      buffer = rest + held;

      const messages: SseMessage[] = [];
      for (const block of blocks) {
        const message = parseBlock(block);
        if (message) messages.push(message);
      }
      return messages;
    },
  };
}
