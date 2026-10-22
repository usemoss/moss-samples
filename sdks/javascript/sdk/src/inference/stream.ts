import {
  InferenceError,
  codeText,
  responseFields,
  transportError,
  type ResponseFields,
} from "./error";
import type { ChatCompletion, ChatCompletionChunk, ChatCompletionMessageToolCall } from "./types";

/** The most UTF-16 code units in one line or in the data of one event. */
const MAX_EVENT = 1 << 20;
/** The most bytes of an error body read for its message. */
const MAX_ERROR_BODY = 1 << 20;

/** A timer that runs only while armed, so a slow reader never trips it. */
interface IdleTimer {
  arm(): void;
  clear(): void;
}

/** Calls `onIdle` when an armed timer runs `ms` milliseconds. Null `ms` never fires. */
export function idleTimer(ms: number | null, onIdle: () => void): IdleTimer {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return {
    arm() {
      clearTimeout(timer);
      if (ms !== null) timer = setTimeout(onIdle, ms);
    },
    clear: () => clearTimeout(timer),
  };
}

/**
 * Reads an error body, arming `idle` while each read waits.
 * It stops after {@link MAX_ERROR_BODY} bytes and cancels the rest of the body.
 */
export async function errorText(response: Response, idle: IdleTimer): Promise<string> {
  if (!response.body) return "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let size = 0;
  try {
    while (size < MAX_ERROR_BODY) {
      idle.arm();
      const { value, done } = await reader.read();
      idle.clear();
      if (done) break;
      size += value.byteLength;
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally {
    reader.cancel().catch(() => {});
  }
}

/** True for the reason of a plain `abort()`, which ends a stream quietly. */
function isAbortError(reason: unknown): boolean {
  return (reason as { name?: unknown } | null)?.name === "AbortError";
}

/** True when the socket ended with no OS error, which undici reports as `UND_ERR_SOCKET`. */
function socketEnded(error: unknown): boolean {
  return (error as { cause?: { code?: unknown } } | null)?.cause?.code === "UND_ERR_SOCKET";
}

/**
 * Yields the data of each server-sent event, joining multi-line data with `\n`.
 * Like any SSE parser, it drops an event that the body ends before its blank line.
 * It splits only the newly read text, so a long line costs time in proportion to its length.
 * A line or the data of one event over {@link MAX_EVENT} throws a `server_error` InferenceError.
 */
async function* sseData(
  body: ReadableStream<Uint8Array>,
  idle: IdleTimer,
  fields: ResponseFields,
): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const tooLarge = () =>
    new InferenceError("The gateway sent an event over 1 MiB.", {
      type: "server_error",
      ...fields,
    });
  let pending = "";
  let data: string[] = [];
  let size = 0;
  try {
    for (;;) {
      idle.arm();
      const { value, done } = await reader.read();
      idle.clear();
      if (done) return;
      const lines = decoder.decode(value, { stream: true }).split("\n");
      lines[0] = pending + lines[0];
      pending = lines.pop() ?? "";
      for (const raw of lines) {
        if (raw.length > MAX_EVENT) throw tooLarge();
        const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
        if (line === "") {
          if (data.length > 0) yield data.join("\n");
          data = [];
          size = 0;
        } else if (line.startsWith("data:")) {
          const part = line.slice(line.startsWith("data: ") ? 6 : 5);
          size += part.length + (data.length > 0 ? 1 : 0);
          if (size > MAX_EVENT) throw tooLarge();
          data.push(part);
        }
      }
      if (pending.length > MAX_EVENT) throw tooLarge();
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

/**
 * The streamed reply of `chat.completions.create` with `stream: true`.
 *
 * Iterate it once with `for await`. Leaving the loop early, or calling
 * `controller.abort()`, ends the loop quietly, closes the connection and stops the model.
 * An abort with any other reason, such as the `TimeoutError` of `AbortSignal.timeout()`, throws it.
 * A failure inside the stream throws an {@link InferenceError} after the chunks that came before it.
 */
export class ChatCompletionStream implements AsyncIterable<ChatCompletionChunk> {
  /** Aborts the request. */
  readonly controller: AbortController;
  #chunks: AsyncIterator<ChatCompletionChunk> | undefined;

  /** @internal */
  constructor(
    response: Response,
    controller: AbortController,
    idle: { arm(): void; clear(): void },
    onSettled: () => void,
  ) {
    this.controller = controller;
    const generator = chunks(response, controller, idle, onSettled);
    this.#chunks = {
      next: () => generator.next(),
      return: (value?: unknown) => {
        controller.abort();
        onSettled();
        return generator.return(value);
      },
    };
  }

  /** Iterates the chunks once. Its `return()` closes the connection, even before the first chunk. */
  [Symbol.asyncIterator](): AsyncIterator<ChatCompletionChunk> {
    const iterator = this.#chunks;
    if (!iterator) throw new Error("A ChatCompletionStream can be iterated only once.");
    this.#chunks = undefined;
    return iterator;
  }
}

async function* chunks(
  response: Response,
  controller: AbortController,
  idle: IdleTimer,
  onSettled: () => void,
): AsyncGenerator<ChatCompletionChunk> {
  const notObject = "The gateway sent an event that is not a JSON object.";
  const fields = responseFields(response);
  let done = false;
  try {
    if (!response.body) {
      throw new InferenceError("The response has no body.", {
        type: "incomplete_stream",
        ...fields,
      });
    }
    for await (const data of sseData(response.body, idle, fields)) {
      if (data === "[DONE]") {
        done = true;
        return;
      }
      let event: {
        error?: { message?: unknown; type?: unknown; code?: unknown };
      } & Partial<ChatCompletionChunk>;
      try {
        event = JSON.parse(data);
      } catch (cause) {
        throw new InferenceError(notObject, { type: "server_error", cause, ...fields });
      }
      if (typeof event !== "object" || event === null || Array.isArray(event)) {
        throw new InferenceError(notObject, { type: "server_error", ...fields });
      }
      if (event.error) {
        const { message, type, code } = event.error;
        throw new InferenceError(
          typeof message === "string" ? message : "The model failed during the stream.",
          {
            type: typeof type === "string" ? type : "model_error",
            errorCode: codeText(code),
            ...fields,
          },
        );
      }
      yield event as ChatCompletionChunk;
    }
    throw new InferenceError("The stream ended before [DONE].", {
      type: "incomplete_stream",
      ...fields,
    });
  } catch (error) {
    if (error instanceof InferenceError) throw error;
    const { aborted, reason } = controller.signal;
    if (aborted) {
      if (isAbortError(reason)) return;
      throw reason;
    }
    if (socketEnded(error)) {
      throw new InferenceError("The connection closed before [DONE].", {
        type: "incomplete_stream",
        cause: error,
        ...fields,
      });
    }
    throw transportError(error, "The connection failed", fields);
  } finally {
    if (!done) controller.abort();
    onSettled();
  }
}

type ChoiceState = {
  content: string | null;
  finishReason: string | null;
  toolCalls: Map<number, ChatCompletionMessageToolCall>;
};

/** Consumes every chunk and builds one completion, as a non-streaming call returns. */
export async function aggregate(
  stream: ChatCompletionStream,
  model: string,
): Promise<ChatCompletion> {
  const choices = new Map<number, ChoiceState>();
  let first: Partial<ChatCompletionChunk> | undefined;
  let usage: ChatCompletion["usage"] = null;
  for await (const chunk of stream) {
    first ??= chunk;
    if (chunk.usage) usage = chunk.usage;
    for (const choice of chunk.choices ?? []) {
      const index = choice.index ?? 0;
      let state = choices.get(index);
      if (!state)
        choices.set(index, (state = { content: null, finishReason: null, toolCalls: new Map() }));
      const delta = choice.delta ?? {};
      if (delta.content) state.content = (state.content ?? "") + delta.content;
      for (const part of delta.tool_calls ?? []) {
        const call = state.toolCalls.get(part.index ?? 0) ?? {
          id: "",
          type: "function",
          function: { name: "", arguments: "" },
        };
        call.id ||= part.id ?? "";
        call.function.name ||= part.function?.name ?? "";
        call.function.arguments += part.function?.arguments ?? "";
        state.toolCalls.set(part.index ?? 0, call);
      }
      if (choice.finish_reason != null) state.finishReason = choice.finish_reason;
    }
  }
  const byIndex = <T>(map: Map<number, T>) => [...map].sort(([a], [b]) => a - b);
  const completion: ChatCompletion = {
    id: first?.id ?? "",
    object: "chat.completion",
    created: first?.created ?? 0,
    model: first?.model ?? model,
    choices: byIndex(choices).map(([index, state]) => ({
      index,
      message: {
        role: "assistant",
        content: state.content,
        ...(state.toolCalls.size > 0 && {
          tool_calls: byIndex(state.toolCalls).map(([, call]) => call),
        }),
      },
      finish_reason: state.finishReason,
    })),
    usage,
  };
  const { signal } = stream.controller;
  if (signal.aborted) throw signal.reason;
  return completion;
}
