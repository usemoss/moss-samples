defmodule Moss.Inference.McpServer do
  @moduledoc """
  An MCP server in the `tools` of a chat completion, whose tools Moss calls during the turn.

  It encodes as JSON to `{"type": "mcp", ...}` without its `nil` fields,
  and `inspect/2` leaves out `server_url` and `headers`, which may hold the server's credentials.
  """

  @derive {Inspect, except: [:server_url, :headers]}
  @enforce_keys [:server_label, :server_url]
  defstruct [:server_label, :server_url, :headers, :allowed_tools, :transport]

  @typedoc """
  An MCP server.

    - `server_label` - its name in the steps: 1 to 32 letters, digits, `_` or `-`
    - `server_url` - an `https` URL on port 443
    - `headers` - at most 16 headers Moss sends the server, such as its credentials
    - `allowed_tools` - names of the server's tools the model may call, else all of them
    - `transport` - `"streamable_http"` (the default) or `"sse"`
  """
  @type t :: %__MODULE__{
          server_label: String.t(),
          server_url: String.t(),
          headers: %{optional(String.t()) => String.t()} | nil,
          allowed_tools: [String.t()] | nil,
          transport: String.t() | nil
        }

  defimpl Jason.Encoder do
    def encode(server, opts) do
      server
      |> Map.from_struct()
      |> Map.reject(fn {_key, value} -> is_nil(value) end)
      |> Map.put(:type, "mcp")
      |> Jason.Encode.map(opts)
    end
  end
end
