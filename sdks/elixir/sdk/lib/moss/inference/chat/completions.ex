defmodule Moss.Inference.Chat.Completions do
  @moduledoc """
  OpenAI's chat completions call, answered by Moss inference.

  Moss searches the named indexes, adds what it finds to the prompt
  and streams the model's reply. `params` is the OpenAI request body as a map,
  so code written for OpenAI's API keeps working once it adds `:indexes`.

      client = Moss.Inference.new("project-id", "project-key")
      messages = [%{role: "user", content: "Do you ship to Canada?"}]

      {:ok, completion} =
        Moss.Inference.Chat.Completions.create(client, %{messages: messages}, indexes: ["faq"])
  """

  alias Moss.Inference
  alias Moss.Inference.{ChatCompletionStream, Error}

  @options [:indexes, :retrieve, :api_key, :timeout, :idle_timeout]

  # Keys of params that belong in opts, each with the option it names.
  @misplaced Enum.map(@options, &{&1, &1}) ++ [apiKey: :api_key]

  @doc """
  Sends a chat completion request with the credentials of `client`.

  `params` is the OpenAI body, with atom or string keys. Every key goes to
  Moss unchanged, except `stream`: with `stream: true` the call returns
  `{:ok, %Moss.Inference.ChatCompletionStream{}}` once the reply starts, and
  without it `{:ok, completion}`, a map with OpenAI's `chat.completion` shape and string keys.
  Without `model`, the call sends `"model" => "moss"`, Moss's own model.
  `params` that hold an option below, or `apiKey`, as an atom or string key, return
  an `invalid_request_error` that names the option, so a provider key never goes in the body.
  A failure returns `{:error, %Moss.Inference.Error{}}`, except one after a
  stream starts, which raises `Moss.Inference.Error` while the stream is read.
  A `client` that is not a `Moss.Inference`, `params` that are not a map
  or an unknown option raises `ArgumentError`, which holds no key.

  Options:
    - `:indexes` - names of the Moss indexes to search, else every index in the project
    - `:retrieve` - `false` skips the search and adds no facts (default `true`)
    - `:api_key` - your own OpenAI, Anthropic or Google key for this call, else the client's.
      A vendor model such as `gpt-4o-mini` needs one, and `moss` ignores it.
    - `:timeout` - milliseconds for the whole call, stream included, else the client's
    - `:idle_timeout` - milliseconds Moss may stay silent, else the client's
  """
  @spec create(Inference.t(), map(), keyword()) ::
          {:ok, ChatCompletionStream.t() | map()} | {:error, Error.t()}
  def create(client, params, opts \\ []) do
    check_arguments!(client, params)
    Inference.check_options!(opts, @options)
    stream? = Map.get(params, :stream, Map.get(params, "stream")) == true
    body = params |> Map.drop([:stream, "stream"]) |> Map.put("stream", true) |> put_model()

    with :ok <- misplaced(params),
         {:ok, headers} <- headers(client, opts),
         {:ok, timeout} <-
           Inference.check_timeout(Keyword.get(opts, :timeout, client.timeout), :timeout),
         {:ok, idle} <-
           Inference.check_timeout(
             Keyword.get(opts, :idle_timeout, client.idle_timeout),
             :idle_timeout
           ),
         {:ok, json} <- encode(body),
         {:ok, stream} <-
           ChatCompletionStream.open(client.endpoint, headers, json, timeout, idle) do
      if stream?, do: {:ok, stream}, else: collect(stream)
    end
  end

  # Checks the client and params of create/3 in its body, since a clause
  # that does not match prints the call's arguments, and with them any key in `opts`.
  defp check_arguments!(client, params) do
    cond do
      not client?(client) ->
        raise ArgumentError, "the client must be a Moss.Inference built by Moss.Inference.new/3"

      not is_map(params) ->
        raise ArgumentError, "the params must be a map"

      true ->
        :ok
    end
  end

  # A client whose URL has the parts a request needs, which one changed by hand may lack.
  defp client?(%Inference{endpoint: %URI{host: host, port: port, path: path}}),
    do: is_binary(host) and is_integer(port) and is_binary(path)

  defp client?(_client), do: false

  defp misplaced(params) do
    Enum.find_value(@misplaced, :ok, fn {key, option} ->
      if Map.has_key?(params, key) or Map.has_key?(params, Atom.to_string(key)),
        do: invalid("Pass #{inspect(option)} in the options of create, not in params.")
    end)
  end

  # Moss's own model, for params that name none.
  defp put_model(body) do
    if Map.has_key?(body, :model) or Map.has_key?(body, "model"),
      do: body,
      else: Map.put(body, "model", "moss")
  end

  # A call's own provider key replaces the client's.
  defp headers(client, opts) do
    with {:ok, indexes} <- indexes(opts[:indexes]),
         {:ok, provider} <- Inference.provider_key(opts[:api_key]) do
      credentials =
        if provider == [],
          do: client.headers,
          else: List.keydelete(client.headers, "x-moss-provider-key", 0) ++ provider

      retrieve = if opts[:retrieve] == false, do: [{"x-moss-retrieve", "off"}], else: []
      {:ok, credentials ++ [{"accept", "text/event-stream"} | indexes] ++ retrieve}
    end
  end

  defp indexes(nil), do: {:ok, []}
  defp indexes([]), do: {:ok, []}

  defp indexes(names) when is_list(names) do
    if Enum.all?(names, &index_name?/1),
      do: {:ok, [{"x-moss-indexes", Enum.join(names, ",")}]},
      else:
        invalid(
          "Index names must be non-empty printable ASCII, without commas or surrounding spaces."
        )
  end

  defp indexes(_names), do: invalid(":indexes must be a list of index names.")

  defp index_name?(name) do
    is_binary(name) and name != "" and not String.contains?(name, ",") and
      Inference.header_safe?(name)
  end

  defp encode(body) do
    case Jason.encode(body) do
      {:ok, json} -> {:ok, json}
      {:error, _} -> invalid("The request params could not be encoded as JSON.")
    end
  end

  defp invalid(message), do: {:error, Error.invalid(message)}

  defp collect(stream) do
    chunks = Enum.to_list(stream)
    first = List.first(chunks, %{})

    {:ok,
     %{
       "id" => first["id"],
       "object" => "chat.completion",
       "created" => first["created"],
       "model" => first["model"],
       "choices" => chunks |> maps("choices") |> by_index() |> Enum.map(&choice/1),
       "usage" => chunks |> Enum.map(& &1["usage"]) |> Enum.reject(&is_nil/1) |> List.last()
     }}
  rescue
    error in Error -> {:error, error}
  end

  defp choice({index, parts}) do
    deltas = Enum.map(parts, &map(&1["delta"]))
    content = deltas |> Enum.map(& &1["content"]) |> Enum.filter(&is_binary/1) |> Enum.join()

    tool_calls = deltas |> maps("tool_calls") |> by_index() |> Enum.map(&tool_call/1)

    message = %{
      "role" => Enum.find_value(deltas, "assistant", & &1["role"]),
      "content" => if(content == "", do: nil, else: content)
    }

    %{
      "index" => index,
      "message" =>
        if(tool_calls == [], do: message, else: Map.put(message, "tool_calls", tool_calls)),
      "finish_reason" =>
        parts |> Enum.map(& &1["finish_reason"]) |> Enum.reject(&is_nil/1) |> List.last()
    }
  end

  defp tool_call({_index, parts}) do
    functions = Enum.map(parts, &map(&1["function"]))

    %{
      "id" => Enum.find_value(parts, & &1["id"]),
      "type" => Enum.find_value(parts, "function", & &1["type"]),
      "function" => %{
        "name" => Enum.find_value(functions, & &1["name"]),
        "arguments" =>
          functions |> Enum.map(& &1["arguments"]) |> Enum.filter(&is_binary/1) |> Enum.join()
      }
    }
  end

  defp by_index(items),
    do: items |> Enum.group_by(&(&1["index"] || 0)) |> Enum.sort_by(&elem(&1, 0))

  # The gateway's lists and objects, read as empty when they have another shape.
  defp maps(parents, key) do
    Enum.flat_map(parents, fn parent ->
      if is_list(parent[key]), do: Enum.map(parent[key], &map/1), else: []
    end)
  end

  defp map(value) when is_map(value), do: value
  defp map(_value), do: %{}
end
