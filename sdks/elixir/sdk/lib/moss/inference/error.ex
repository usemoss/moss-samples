defmodule Moss.Inference.Error do
  @moduledoc """
  The error of every inference call and stream.

  `Moss.Inference.new/3` raises it for a bad credential, option or `MOSS_INFERENCE_URL`,
  `Moss.Inference.Chat.Completions.create/3` returns it as `{:error, error}`,
  and a `Moss.Inference.ChatCompletionStream` raises it when the reply fails mid-stream.

  `type` is the gateway's `error.type` as sent, such as `"invalid_request_error"` or
  `"model_error"`, and on a 429 `"requests"`, `"tokens"` or `"capacity"`. Match a rate
  limit on `status` 429, and read its `code`, such as `"rate_limit_exceeded"`, and `retry_after`.
  Without a type, `type` follows the HTTP status: 401 `"authentication_error"`,
  403 `"permission_error"`, 404 `"not_found_error"`, 429 `"rate_limit_error"`, any other 4xx
  `"invalid_request_error"`, and any other status, such as a 3xx or 5xx, `"server_error"`.
  The SDK follows no redirect, so a 3xx reply is an error too. A request that never reached
  the gateway, or a connection that failed mid-reply, has `"connection_error"`, and one that
  ran out of time has `"timeout"`. A reply that ends before `[DONE]` has `"incomplete_stream"`,
  and an argument rejected before any request has `"invalid_request_error"`.

  `status` is the HTTP status of an error reply, else `nil`.
  `message` is the gateway's `error.message` or `detail`, else the
  start of a body that is not JSON, else the status line of the reply.
  `code` is the gateway's `error.code`, such as `"rate_limit_exceeded"`, with
  a number as its decimal text, from an error reply or an error event, else `nil`.
  `request_id` is the reply's `X-Moss-Request-Id` header, for any failure once a
  reply has come, and `nil` for a refused argument or a failure before any reply.
  `retry_after` is the error reply's `Retry-After` header in milliseconds, when it
  holds whole seconds, else `nil`. A failure after a 2xx reply has none.

      case Moss.Inference.Chat.Completions.create(client, params, indexes: ["faq"]) do
        {:ok, completion} -> completion
        {:error, %Moss.Inference.Error{retry_after: ms}} when is_integer(ms) -> {:retry_in, ms}
        {:error, error} -> {:failed, error.request_id}
      end
  """

  @type t :: %__MODULE__{
          status: pos_integer() | nil,
          type: String.t(),
          message: String.t(),
          code: String.t() | nil,
          request_id: String.t() | nil,
          retry_after: non_neg_integer() | nil
        }

  defexception [:status, :type, :message, :code, :request_id, :retry_after]

  @doc false
  @spec invalid(String.t()) :: t()
  def invalid(message), do: %__MODULE__{type: "invalid_request_error", message: message}
end

defimpl String.Chars, for: Moss.Inference.Error do
  def to_string(%Moss.Inference.Error{message: message}), do: message
end
