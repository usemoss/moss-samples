import { InferenceError, codeText, transportError, type ResponseFields } from "./error";
import type {
  ChatCompletion,
  ChatCompletionChunk,
  ChatCompletionLogprobs,
  ChatCompletionMessageToolCall,
  ToolStep,
} from "./types";

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
 * A failure inside the stream throws an {@link InferenceError} after the chunks that came before it,
 * with `errorCode` `failed_after_tool_call` once a chunk carried a `moss_tool_step`.
 */
export class ChatCompletionStream implements AsyncIterable<ChatCompletionChunk> {
  /** Aborts the request. */
  readonly controller: AbortController;
  /** The `X-Moss-Request-Id` of the response, undefined when it has none. */
  readonly requestId: string | undefined;
  #chunks: AsyncIterator<ChatCompletionChunk> | undefined;
  readonly #next: () => Promise<IteratorResult<ChatCompletionChunk>>;
  readonly #join: Join;
  /** What reading the chunks threw, which the completion throws again. */
  #failure: { error: unknown } | undefined;
  #final: Promise<ChatCompletion> | undefined;

  /** @internal */
  constructor(
    response: Response,
    controller: AbortController,
    idle: { arm(): void; clear(): void },
    onSettled: () => void,
    fields: { requestId?: string; errorCode?: "failed_after_tool_call" },
    model: string,
  ) {
    this.controller = controller;
    this.requestId = fields.requestId;
    this.#join = new Join(model);
    const generator = chunks(response, controller, idle, onSettled, fields);
    this.#next = async () => {
      try {
        const result = await generator.next();
        if (!result.done) this.#join.add(result.value);
        return result;
      } catch (error) {
        this.#failure = { error };
        throw error;
      }
    };
    this.#chunks = {
      next: this.#next,
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

  /**
   * The whole stream joined into one completion, as a call without `stream: true` returns.
   *
   * Every call returns the same completion.
   * Call it after the loop ends, or instead of one.
   * It reads the chunks the loop has not read, then joins them with the ones it has.
   * It rejects with what the loop throws, or with the signal's reason after an abort.
   */
  finalChatCompletion(): Promise<ChatCompletion> {
    return (this.#final ??= this.#drain());
  }

  async #drain(): Promise<ChatCompletion> {
    while (!(await this.#next()).done);
    if (this.#failure) throw this.#failure.error;
    const { signal } = this.controller;
    if (signal.aborted) throw signal.reason;
    return Object.defineProperty(this.#join.build(), "requestId", { value: this.requestId });
  }
}

async function* chunks(
  response: Response,
  controller: AbortController,
  idle: IdleTimer,
  onSettled: () => void,
  fields: ResponseFields,
): AsyncGenerator<ChatCompletionChunk> {
  const notObject = "The gateway sent an event that is not a JSON object.";
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
      if (event.moss_tool_step) fields.errorCode = "failed_after_tool_call";
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
  logprobs: ChatCompletionLogprobs | null;
  finishReason: string | null;
  toolCalls: Map<number, ChatCompletionMessageToolCall>;
  /** The slot of the latest tool call piece, or -1 before the first. */
  last: number;
};

/** True for a JSON object, not null or an array. */
const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Joins chunks as they pass into one completion, as a non-streaming call returns.
 *
 * It joins tool call pieces as the gateway does, keeping fields beyond OpenAI's.
 * A piece with no integer `index` joins the call that has its `id`, else the latest call.
 * A new `id` starts the next call instead, unless the latest call has no id yet and takes it.
 */
class Join {
  readonly choices = new Map<number, ChoiceState>();
  readonly steps: ToolStep[] = [];
  first: Partial<ChatCompletionChunk> | undefined;
  usage: ChatCompletion["usage"] = null;

  constructor(readonly model: string) {}

  add(chunk: ChatCompletionChunk): void {
    this.first ??= chunk;
    if (chunk.usage) this.usage = chunk.usage;
    if (chunk.moss_tool_step) this.steps.push(chunk.moss_tool_step);
    for (const choice of Array.isArray(chunk.choices) ? chunk.choices : []) {
      if (!isObject(choice)) continue;
      const index = choice.index ?? 0;
      let state = this.choices.get(index);
      if (!state) {
        state = {
          content: null,
          logprobs: null,
          finishReason: null,
          toolCalls: new Map(),
          last: -1,
        };
        this.choices.set(index, state);
      }
      const delta = choice.delta ?? {};
      if (delta.content) state.content = (state.content ?? "") + delta.content;
      if (isObject(choice.logprobs)) {
        state.logprobs ??= { content: null, refusal: null };
        for (const key of ["content", "refusal"] as const) {
          const tokens = choice.logprobs[key];
          if (Array.isArray(tokens)) (state.logprobs[key] ??= []).push(...tokens);
        }
      }
      const parts = Array.isArray(delta.tool_calls) ? delta.tool_calls : [];
      for (const part of parts) {
        if (!isObject(part)) continue;
        let slot = part.index;
        if (!Number.isInteger(slot)) {
          const known = [...state.toolCalls].find(([, joined]) => part.id && joined.id === part.id);
          const latest = state.toolCalls.get(state.last);
          if (known) slot = known[0];
          else if (latest && !(part.id && latest.id)) slot = state.last;
          else slot = Math.max(-1, ...state.toolCalls.keys()) + 1;
        }
        state.last = slot;
        const call: ChatCompletionMessageToolCall = state.toolCalls.get(slot) ?? {
          id: "",
          type: "function",
          function: { name: "", arguments: "" },
        };
        if (part.id) call.id = part.id;
        if (part.type) call.type = part.type;
        if (part.function?.name) call.function.name = part.function.name;
        if (typeof part.function?.arguments === "string")
          call.function.arguments += part.function.arguments;
        for (const [key, value] of Object.entries(part)) {
          if (value == null || ["index", "id", "type", "function"].includes(key)) continue;
          const merged =
            isObject(value) && isObject(call[key]) ? { ...call[key], ...value } : value;
          Object.defineProperty(call, key, {
            value: merged,
            enumerable: true,
            writable: true,
            configurable: true,
          });
        }
        state.toolCalls.set(slot, call);
      }
      if (choice.finish_reason != null) state.finishReason = choice.finish_reason;
    }
  }

  build(): ChatCompletion {
    const byIndex = <T>(map: Map<number, T>) => [...map].sort(([a], [b]) => a - b);
    return {
      id: this.first?.id ?? "",
      object: "chat.completion",
      created: this.first?.created ?? 0,
      model: this.first?.model ?? this.model,
      choices: byIndex(this.choices).map(([index, state]) => ({
        index,
        message: {
          role: "assistant",
          content: state.content ?? (state.toolCalls.size > 0 ? null : ""),
          ...(state.toolCalls.size > 0 && {
            tool_calls: byIndex(state.toolCalls).map(([, call]) => call),
          }),
        },
        logprobs: state.logprobs,
        finish_reason: state.finishReason,
      })),
      usage: this.usage,
      ...(this.steps.length > 0 && { moss_tool_steps: this.steps }),
    };
  }
}
