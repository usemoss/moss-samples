defmodule Moss.Inference do
  @moduledoc """
  A client for Moss inference, which answers OpenAI's chat completions call.

  Moss searches your indexes, adds what it finds to the prompt and streams the reply.
  A client holds the project credentials, the gateway URL, an optional provider key
  and default timeouts and retries. It is plain data, so build it once and pass it to any process.
  Calls from any process reuse idle connections.

      client = Moss.Inference.new("project-id", "project-key")
      messages = [%{role: "user", content: "Do you ship to Canada?"}]

      {:ok, completion} =
        Moss.Inference.Chat.Completions.create(client, %{messages: messages}, indexes: ["faq"])

  See `Moss.Inference.Chat.Completions.create/3` for the call itself.
  """

  alias Moss.Inference.Error

  @options [:api_key, :timeout, :idle_timeout, :max_retries]

  @base_url "https://inference.moss.dev/v1"

  @derive {Inspect, only: [:project_id, :timeout, :idle_timeout, :max_retries]}
  @enforce_keys [:project_id, :endpoint, :headers, :timeout, :idle_timeout, :max_retries]
  defstruct @enforce_keys

  @typedoc """
  A client. Fields other than `project_id` are internal.
  `inspect/2` leaves out the credentials the client holds,
  and the gateway URL comes only from `MOSS_INFERENCE_URL`.
  """
  @type t :: %__MODULE__{
          project_id: String.t(),
          endpoint: URI.t(),
          headers: [{String.t(), String.t()}],
          timeout: timeout(),
          idle_timeout: timeout(),
          max_retries: non_neg_integer()
        }

  @doc """
  Builds a client and checks its credentials, options and gateway URL.

  A bad credential or option raises `Moss.Inference.Error` with type `"invalid_request_error"`,
  so a client that builds can make calls. An unknown option raises `ArgumentError`.
  No key ever appears in an error or in `inspect/2`.

  The client calls `https://inference.moss.dev/v1`, or the base URL in the `MOSS_INFERENCE_URL`
  environment variable, which `new/3` reads. It must be an `http` or `https` URL with a host and no user info, query or fragment,
  or `new/3` raises an error that names the variable and leaves out its value.

  Options:
    - `:api_key` - your own OpenAI, Anthropic or Google key, for a vendor model such
      as `gpt-4o-mini`. `moss` ignores it, and a vendor model without one is refused.
      A call's own `:api_key` wins over this one.
    - `:timeout` - milliseconds for a whole call, stream included (default `:infinity`)
    - `:idle_timeout` - milliseconds Moss may stay silent, before the reply
      headers or between two parts of the body (default `120_000`, `:infinity` disables it)
    - `:max_retries` - how many times a failed call is sent again before its reply starts
      (default `2`, `0` turns retries off)
  """
  @spec new(String.t(), String.t(), keyword()) :: t()
  def new(project_id, project_key, opts \\ []) do
    check_options!(opts, @options)

    with :ok <- credential(project_id, "project id"),
         :ok <- credential(project_key, "project key"),
         :ok <-
           if(project_id =~ ":", do: invalid("The project id must not contain \":\"."), else: :ok),
         {:ok, provider} <- provider_key(opts[:api_key]),
         {:ok, timeout} <- check_timeout(Keyword.get(opts, :timeout, :infinity), :timeout),
         {:ok, idle_timeout} <-
           check_timeout(Keyword.get(opts, :idle_timeout, 120_000), :idle_timeout),
         {:ok, max_retries} <- check_retries(Keyword.get(opts, :max_retries, 2)),
         {:ok, endpoint} <- endpoint(System.get_env("MOSS_INFERENCE_URL", "")) do
      %__MODULE__{
        project_id: project_id,
        endpoint: endpoint,
        headers: [{"authorization", "Bearer #{project_id}:#{project_key}"} | provider],
        timeout: timeout,
        idle_timeout: idle_timeout,
        max_retries: max_retries
      }
    else
      {:error, error} -> raise error
    end
  end

  # Names only the unknown keys, since the values may hold a key.
  @doc false
  @spec check_options!(term(), [atom()]) :: :ok
  def check_options!(opts, allowed) do
    unless Keyword.keyword?(opts), do: raise(ArgumentError, "the options must be a keyword list")

    case for({key, _value} <- opts, key not in allowed, do: key) do
      [] ->
        :ok

      unknown ->
        raise ArgumentError, "unknown options #{inspect(unknown)}, expected #{inspect(allowed)}"
    end
  end

  # The chat completions URL under a base URL, or @base_url when it is empty.
  defp endpoint(""), do: endpoint(@base_url)

  defp endpoint(base) do
    with {:ok, %URI{scheme: scheme, userinfo: nil, query: nil, fragment: nil} = uri}
         when scheme in ["http", "https"] <- URI.new(base),
         true <- uri.host not in [nil, ""] and uri.port in 1..65_535 do
      {:ok, %{uri | path: String.replace_suffix(uri.path || "", "/", "") <> "/chat/completions"}}
    else
      _invalid ->
        invalid(
          "MOSS_INFERENCE_URL must be an http or https URL with a host, " <>
            "and no user info, query or fragment."
        )
    end
  end

  defp credential(value, name) do
    cond do
      not is_binary(value) or value == "" ->
        invalid("The #{name} must be a non-empty string.")

      not header_safe?(value) ->
        invalid("The #{name} must be printable ASCII without surrounding spaces.")

      true ->
        :ok
    end
  end

  # The X-Moss-Provider-Key header of an :api_key, none for nil, and an error for "".
  @doc false
  @spec provider_key(term()) :: {:ok, [{String.t(), String.t()}]} | {:error, Error.t()}
  def provider_key(nil), do: {:ok, []}
  def provider_key(""), do: invalid(":api_key must not be empty.")

  def provider_key(key) do
    if is_binary(key) and header_safe?(key),
      do: {:ok, [{"x-moss-provider-key", key}]},
      else: invalid(":api_key must be a string of printable ASCII without surrounding spaces.")
  end

  @doc false
  @spec check_timeout(term(), atom()) :: {:ok, timeout()} | {:error, Error.t()}
  def check_timeout(:infinity, _name), do: {:ok, :infinity}
  def check_timeout(ms, _name) when is_integer(ms) and ms > 0, do: {:ok, ms}
  def check_timeout(_ms, name), do: invalid(":#{name} must be a positive integer or :infinity.")

  @doc false
  @spec check_retries(term()) :: {:ok, non_neg_integer()} | {:error, Error.t()}
  def check_retries(count) when is_integer(count) and count >= 0, do: {:ok, count}
  def check_retries(_count), do: invalid(":max_retries must be a non-negative integer.")

  # Checked before any request, so a bad value fails without being echoed.
  # A value HTTP carries as is holds bytes Mint accepts and no space or tab at either end.
  @doc false
  @spec header_safe?(String.t()) :: boolean()
  def header_safe?(value), do: not String.match?(value, ~r/[^\t\x20-\x7e]|\A[\t ]|[\t ]\z/)

  defp invalid(message), do: {:error, Error.invalid(message)}
end
