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

  @options [:indexes, :retrieve, :cache, :api_key, :timeout, :idle_timeout, :max_retries]

  # Keys of params that belong in opts, each with the option it names.
  @misplaced Enum.map(@options, &{&1, &1}) ++ [apiKey: :api_key]

  @typedoc """
  The OpenAI request body, with atom or string keys, sent as it is. Among them:

    - `tools` - what the model may call: OpenAI function tools such as
      `%{type: "function", function: %{name: "lookup", parameters: schema}}`,
      `Moss.Inference.McpServer` structs, or any other map
    - `tool_choice` - `"none"`, `"auto"`, `"required"`, or a map such as
      `%{type: "function", function: %{name: "lookup"}}`
    - `parallel_tool_calls` - `false` limits the model to one tool call per reply
  """
  @type params :: %{optional(atom() | String.t()) => term()}

  @doc """
  Sends a chat completion request with the credentials of `client`.

  `params` is the OpenAI body, with atom or string keys. Every key goes to
  Moss unchanged, except `stream`: with `stream: true` the call returns
  `{:ok, %Moss.Inference.ChatCompletionStream{}}` once the reply starts, and
  without it `{:ok, completion}`, a map with OpenAI's `chat.completion` shape and string keys.
  Its tool calls keep every field the model sent, so its message goes back in `messages` as it is,
  `"moss_tool_steps"` lists the MCP steps, when there are any, and `"request_id"` is the reply's
  `X-Moss-Request-Id` header, else `nil`.
  Without `model`, the call sends `"model" => "moss"`, Moss's own model.
  `params` that hold an option below, or `apiKey`, as an atom or string key, return
  an `invalid_request_error` that names the option, so a provider key never goes in the body.
  A key given twice in one map, such as `:content` and `"content"`, returns one too.
  A failure returns `{:error, %Moss.Inference.Error{}}`, except one after a
  stream starts, which raises `Moss.Inference.Error` while the stream is read.
  A call whose connection fails, or that gets a 408, 409, 429 or 5xx reply, is sent again
  up to `:max_retries` times, after the reply's `Retry-After` seconds when they are 60 or fewer,
  else after 0.5 s doubled each time up to 8 s, less up to 25%. The waits count against `:timeout`,
  and a wait that would pass it returns the error instead. A reply's `x-should-retry` header of
  `false` forbids a retry and `true` forces one. A stream that started is never sent again.
  A `client` that is not a `Moss.Inference`, `params` that are not a map
  or an unknown option raises `ArgumentError`, which holds no key.

  Options:
    - `:indexes` - names of the Moss indexes to search, `[]` for none,
      else every index in the project
    - `:retrieve` - `false` skips the search and adds no facts (default `true`)
    - `:cache` - `false` always asks the model, never Moss's reply cache (default `true`)
    - `:api_key` - your own OpenAI, Anthropic or Google key for this call, else the client's.
      A vendor model such as `gpt-4o-mini` needs one, and `moss` ignores it.
    - `:timeout` - milliseconds for the whole call, stream included, else the client's
    - `:idle_timeout` - milliseconds Moss may stay silent, else the client's
    - `:max_retries` - how many times a failed call is sent again, else the client's
  """
  @spec create(Inference.t(), params(), keyword()) ::
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
         {:ok, retries} <-
           Inference.check_retries(Keyword.get(opts, :max_retries, client.max_retries)),
         {:ok, json} <- encode(body),
         {:ok, stream} <-
           ChatCompletionStream.open(client.endpoint, headers, json, timeout, idle, retries) do
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

      retrieve? = opts[:retrieve] != false and opts[:indexes] != []
      retrieve = if retrieve?, do: [], else: [{"x-moss-retrieve", "off"}]
      cache = if opts[:cache] == false, do: [{"x-moss-cache", "off"}], else: []
      {:ok, credentials ++ [{"accept", "text/event-stream"} | indexes] ++ retrieve ++ cache}
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

  # Refuses a key given twice, such as :content and "content", since Moss would read only one.
  defp encode(body) do
    case Jason.encode(body, maps: :strict) do
      {:ok, json} ->
        {:ok, json}

      {:error, %Jason.EncodeError{message: "duplicate key: " <> _key}} ->
        invalid("A params key is given twice, for example as an atom and as a string.")

      {:error, _error} ->
        invalid("The request params could not be encoded as JSON.")
    end
  end

  defp invalid(message), do: {:error, Error.invalid(message)}

  defp collect(stream) do
    chunks = Enum.to_list(stream)
    first = List.first(chunks, %{})
    steps = for %{"moss_tool_step" => %{} = step} <- chunks, do: step

    completion = %{
      "id" => first["id"],
      "object" => "chat.completion",
      "created" => first["created"],
      "model" => first["model"],
      "choices" => chunks |> maps("choices") |> by_index() |> Enum.map(&choice/1),
      "usage" => chunks |> Enum.map(& &1["usage"]) |> Enum.reject(&is_nil/1) |> List.last(),
      "request_id" => stream.request_id
    }

    {:ok, if(steps == [], do: completion, else: Map.put(completion, "moss_tool_steps", steps))}
  rescue
    error in Error -> {:error, error}
  end

  # A joined choice. Its message always has content, so it goes back in messages as it is.
  defp choice({index, parts}) do
    deltas = Enum.map(parts, &map(&1["delta"]))
    content = deltas |> Enum.map(& &1["content"]) |> Enum.filter(&is_binary/1) |> Enum.join()

    {tool_calls, _last} =
      for %{"tool_calls" => pieces} <- deltas,
          is_list(pieces),
          %{} = piece <- pieces,
          reduce: {%{}, nil} do
        {calls, last} ->
          slot = slot(piece, calls, last)
          {merge_call(calls, piece, slot), slot}
      end

    tool_calls = tool_calls |> Enum.sort() |> Enum.map(&elem(&1, 1))

    message = %{
      "role" => Enum.find_value(deltas, "assistant", & &1["role"]),
      "content" => if(content == "" and tool_calls != [], do: nil, else: content)
    }

    %{
      "index" => index,
      "message" =>
        if(tool_calls == [], do: message, else: Map.put(message, "tool_calls", tool_calls)),
      "logprobs" => parts |> Enum.map(& &1["logprobs"]) |> Enum.filter(&is_map/1) |> logprobs(),
      "finish_reason" =>
        parts |> Enum.map(& &1["finish_reason"]) |> Enum.reject(&is_nil/1) |> List.last()
    }
  end

  # The logprobs the chunks sent, each key's lists joined in order, and nil for a key none sent.
  defp logprobs([]), do: nil

  defp logprobs(sent) do
    Map.new(~w(content refusal), fn key ->
      lists = for %{^key => list} when is_list(list) <- sent, do: list
      {key, if(lists == [], do: nil, else: Enum.concat(lists))}
    end)
  end

  # A piece's integer index, else the call that has the piece's id, else the most recent call.
  # The first piece, or a new id when the most recent call has an id, starts a call in the next free slot.
  defp slot(%{"index" => index}, _calls, _last) when is_integer(index), do: index

  defp slot(piece, calls, last) do
    id = piece["id"]
    id? = is_binary(id) and id != ""
    owner = Enum.find_value(calls, fn {slot, call} -> if id? and call["id"] == id, do: slot end)
    next = Enum.max(Map.keys(calls), fn -> -1 end) + 1

    cond do
      owner -> owner
      last == nil or (id? and calls[last]["id"] != "") -> next
      true -> last
    end
  end

  # Folds a tool call piece into the call at `slot`. A new call has "" for id, name and arguments.
  # A set id, type or name replaces, arguments append, and a map field merges into the last one.
  defp merge_call(calls, piece, slot) do
    empty = %{"id" => "", "type" => "function", "function" => %{"name" => "", "arguments" => ""}}
    call = Map.get(calls, slot, empty)
    function = map(piece["function"])
    arguments = if is_binary(function["arguments"]), do: function["arguments"], else: ""

    extras =
      Map.reject(piece, fn {key, value} -> key in ~w(index id type function) or value == nil end)

    call =
      call
      |> Map.merge(extras, fn _key, old, new ->
        if is_map(old) and is_map(new), do: Map.merge(old, new), else: new
      end)
      |> put_set("id", piece["id"])
      |> put_set("type", piece["type"])
      |> update_in(["function"], &put_set(&1, "name", function["name"]))
      |> update_in(["function", "arguments"], &(&1 <> arguments))

    Map.put(calls, slot, call)
  end

  # Puts a value Python counts as true, as the gateway does: not null, false, 0, "", [] or {}.
  defp put_set(map, _key, value) when value in [nil, false, "", [], %{}] or value == 0, do: map
  defp put_set(map, key, value), do: Map.put(map, key, value)

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
