defmodule Moss.Error do
  @moduledoc """
  The reason in every `{:error, reason}` this SDK returns.

  `code` is an atom a caller can match on: `:invalid_argument`, `:not_found`,
  `:unauthorized`, `:network`, `:deserialization`, `:model_unavailable` or
  `:internal`. `message` is fixed text for each kind of failure and carries no
  URLs, file paths or index names. `detail` holds the native core's error text,
  for logs and support rather than a stable contract, and is `nil` when there is none.

  `Moss.Error` is an exception, so `raise reason` works, and it implements
  `String.Chars`, so `"\#{reason}"` renders the message.

      case Moss.Client.load_index(client, "docs") do
        {:ok, info} -> info
        {:error, %Moss.Error{code: :not_found}} -> nil
      end
  """

  @type code ::
          :invalid_argument
          | :not_found
          | :unauthorized
          | :network
          | :deserialization
          | :model_unavailable
          | :internal

  @type t :: %__MODULE__{code: code(), message: String.t(), detail: String.t() | nil}

  defexception [:code, :message, :detail]

  @doc false
  @spec invalid_argument(String.t()) :: t()
  def invalid_argument(message) when is_binary(message) do
    %__MODULE__{code: :invalid_argument, message: message, detail: nil}
  end
end

defimpl String.Chars, for: Moss.Error do
  def to_string(%Moss.Error{message: message}), do: message
end
