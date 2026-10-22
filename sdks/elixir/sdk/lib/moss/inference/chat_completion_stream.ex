defmodule Moss.Inference.ChatCompletionStream do
  @moduledoc """
  A streamed chat completion: an `Enumerable` of chunk maps, as decoded from the reply.

  Each chunk has OpenAI's `chat.completion.chunk` shape with string keys, such as
  `chunk["choices"]` and `choice["delta"]["content"]`. A final chunk may carry `"usage"`
  with an empty `"choices"` list. A failure once the reply has started raises
  `Moss.Inference.Error` where it happens, after the chunks that came before it.
  An event or line over 1 MiB raises `"server_error"` and closes the connection.
  A connection reset raises `"incomplete_stream"`, since Erlang's `:ssl` reports it as a close.

  The connection belongs to the process that called
  `Moss.Inference.Chat.Completions.create/3`, so enumerate the stream there, and only once.
  A stream read to its end gives its connection back for the next call.
  Halting early, for example with `Enum.take/2`, closes the connection and stops the model,
  and so does a failure. `close/1` does the same from any process, after which the stream
  ends without an error.
  """

  alias Moss.Inference.{Error, Pool}

  @connect_timeout 10_000
  @drain_timeout 1_000
  @body_part 65_536
  @error_body 65_536

  # The most bytes one line, or the data of one event, may hold.
  @event_limit 1_048_576
  @too_large %{"type" => "server_error", "message" => "The gateway sent an event over 1 MiB."}

  # Slots of the flags every copy of a stream shares.
  @claimed 1
  @connection 2

  # The @connection slot: the stream holds it, close/1 closed it, or the stream let it go.
  @open 0
  @closed 1
  @released 2

  # `details` holds the error fields each failure of the reply carries.
  @derive {Inspect, only: []}
  defstruct [:conn, :received, :owner, :limits, :flags, :origin, :details]

  @typedoc "A stream. Its fields are internal."
  @type t :: %__MODULE__{}

  @doc """
  Closes the connection of a stream that will not be read to the end.

  A stream that already ended has let its connection go, and is left as it is.
  """
  @spec close(t()) :: :ok
  def close(%__MODULE__{conn: conn, flags: flags}) do
    if :atomics.compare_exchange(flags, @connection, @open, @closed) == :ok,
      do: Mint.HTTP1.close(conn)

    :ok
  end

  # The calling process owns the connection and reads it,
  # and only a reply read to its end gives it back to the pool.
  @doc false
  @spec open(URI.t(), [{String.t(), String.t()}], binary(), timeout(), timeout()) ::
          {:ok, t()} | {:error, Error.t()}
  def open(%URI{} = uri, headers, body, timeout, idle_timeout) do
    limits = {if(timeout == :infinity, do: :infinity, else: now() + timeout), idle_timeout}
    headers = [{"content-type", "application/json"} | headers]

    # A host with a colon is an IPv6 address, which Mint reaches only with inet6.
    options = [
      mode: :passive,
      optional_responses: [:status_reason],
      transport_opts: [
        send_timeout: min(idle_timeout, timeout),
        send_timeout_close: true,
        inet6: String.contains?(uri.host, ":")
      ]
    ]

    with {:ok, conn} <- connection(uri, options, limits) do
      case request(conn, uri.path, headers, body) do
        {:ok, conn} -> await_start(conn, origin(uri), limits, [])
        {:error, conn, reason} -> await_start(conn, origin(uri), limits, [{:failed, reason}])
      end
    else
      {:error, %Mint.TransportError{reason: :timeout}} -> {:error, timeout_error()}
      {:error, reason} -> {:error, unreachable(reason)}
    end
  end

  # An idle connection the gateway has not closed, else a new one.
  #
  # A pooled connection is checked before anything is written to it,
  # so replacing a closed one never sends the call twice. Over TLS the check
  # sees only what the ssl process already read, and the pool catches a close while idle.
  # One that comes back after the call ran out of time goes back unused, and the call times out.
  defp connection(uri, options, {deadline, _idle} = limits) do
    case Pool.checkout(origin(uri), connect_time(limits), deadline) do
      nil ->
        connect(uri, options, limits)

      conn ->
        cond do
          remaining(deadline) == 0 ->
            Pool.checkin(origin(uri), conn)
            {:error, %Mint.TransportError{reason: :timeout}}

          open?(conn, uri, options[:transport_opts][:send_timeout]) ->
            {:ok, conn}

          true ->
            Mint.HTTP1.close(conn)
            connect(uri, options, limits)
        end
    end
  end

  # A call with no time left times out before it connects.
  defp connect(uri, options, limits) do
    case connect_time(limits) do
      0 ->
        {:error, %Mint.TransportError{reason: :timeout}}

      time ->
        options = put_in(options, [:transport_opts, :timeout], time)
        Mint.HTTP1.connect(scheme(uri), uri.host, uri.port, options)
    end
  end

  # How long a checkout or a new connection may take:
  # the call's time left, within the idle limit and @connect_timeout.
  defp connect_time({deadline, idle}), do: Enum.min([@connect_timeout, remaining(deadline), idle])

  # A read that times out at once found no close and no stray bytes.
  defp open?(conn, uri, send_timeout) do
    case Mint.HTTP1.recv(conn, 0, 0) do
      {:error, _conn, %Mint.TransportError{reason: :timeout}, []} ->
        setopts(uri, Mint.HTTP1.get_socket(conn), send_timeout: send_timeout) == :ok

      _closed_or_stray_bytes ->
        false
    end
  end

  defp setopts(%URI{scheme: "https"}, socket, opts), do: :ssl.setopts(socket, opts)
  defp setopts(_uri, socket, opts), do: :inet.setopts(socket, opts)

  defp origin(uri), do: {scheme(uri), uri.host, uri.port}

  # Sends the body in parts, since send_timeout only limits a send that waits behind another.
  defp request(conn, target, headers, body) do
    headers = [{"content-length", Integer.to_string(byte_size(body))} | headers]

    with {:ok, conn, ref} <- Mint.HTTP1.request(conn, "POST", target, headers, :stream),
         do: send_body(conn, ref, body)
  end

  defp send_body(conn, ref, <<part::binary-size(@body_part), rest::binary>>) when rest != "" do
    with {:ok, conn} <- Mint.HTTP1.stream_request_body(conn, ref, part),
         do: send_body(conn, ref, rest)
  end

  defp send_body(conn, ref, body) do
    with {:ok, conn} <- Mint.HTTP1.stream_request_body(conn, ref, body),
         do: Mint.HTTP1.stream_request_body(conn, ref, :eof)
  end

  defp scheme(%URI{scheme: "https"}), do: :https
  defp scheme(_uri), do: :http

  defp await_start(conn, origin, limits, received) do
    case Enum.split_while(received, &(elem(&1, 0) not in [:headers, :failed])) do
      {head, [{:headers, _ref, headers} | rest]} ->
        if informational?(head),
          do: await_start(conn, origin, limits, rest),
          else: start(%{conn: conn, received: rest, origin: origin}, limits, head, headers)

      {_head, [{:failed, %Mint.TransportError{reason: :timeout}} | _]} ->
        Mint.HTTP1.close(conn)
        {:error, timeout_error(limits)}

      {_head, [{:failed, reason} | _]} ->
        Mint.HTTP1.close(conn)
        {:error, unreachable(reason)}

      {_head, []} ->
        {conn, more} = recv(conn, limits)
        await_start(conn, origin, limits, received ++ more)
    end
  end

  # A reply such as 103 Early Hints, which comes before the final one.
  defp informational?(head) do
    match?(
      {:status, _ref, status} when status in 100..199 and status != 101,
      List.keyfind(head, :status, 0)
    )
  end

  defp start(state, limits, head, headers) do
    {:status, _ref, status} = List.keyfind(head, :status, 0)

    if status in 200..299 do
      {:ok,
       %__MODULE__{
         conn: state.conn,
         received: state.received,
         owner: self(),
         limits: limits,
         flags: :atomics.new(2, []),
         origin: state.origin,
         details: %{request_id: request_id(headers)}
       }}
    else
      {ending, body, state} = read_body(state, limits, "")
      Mint.HTTP1.close(state.conn)
      {deadline, _idle} = limits

      error =
        if match?({:failed, %Mint.TransportError{reason: :timeout}}, ending) or
             remaining(deadline) == 0 do
          timeout_error(limits)
        else
          phrase = for {:status_reason, _ref, phrase} <- head, into: "", do: phrase
          status_error(status, phrase, body)
        end

      {:error, %{error | request_id: request_id(headers), retry_after: retry_after(headers)}}
    end
  end

  defp request_id(headers) do
    case List.keyfind(headers, "x-moss-request-id", 0) do
      {_name, id} when id != "" -> id
      _none -> nil
    end
  end

  # An error reply's Retry-After in ms, when it holds whole seconds.
  defp retry_after(headers) do
    case List.keyfind(headers, "retry-after", 0) do
      {_name, seconds} -> if seconds =~ ~r/\A[0-9]+\z/, do: String.to_integer(seconds) * 1000
      nil -> nil
    end
  end

  # How reading an error reply's body ended, and the first 64 KiB of it.
  defp read_body(state, limits, acc) do
    case await_part(state, limits) do
      {:part, part, state} when byte_size(acc) + byte_size(part) < @error_body ->
        read_body(state, limits, acc <> part)

      {:part, part, state} ->
        {:full, binary_part(acc <> part, 0, @error_body), state}

      {ending, state} ->
        {ending, acc, state}
    end
  end

  defp status_error(status, phrase, body) do
    {type, message, code} =
      case Jason.decode(body) do
        {:ok, %{"error" => %{} = error}} -> {error["type"], error["message"], code(error)}
        {:ok, %{"detail" => detail}} when is_binary(detail) -> {nil, detail, nil}
        {:ok, %{"detail" => detail}} when detail != nil -> {nil, Jason.encode!(detail), nil}
        {:ok, _other} -> {nil, nil, nil}
        {:error, _not_json} -> {nil, excerpt(body), nil}
      end

    %Error{
      status: status,
      type: if(is_binary(type), do: type, else: status_type(status)),
      message: if(is_binary(message), do: message, else: String.trim("HTTP #{status} #{phrase}")),
      code: code
    }
  end

  # The gateway's error.code as text: a string as it is, an integer in decimal.
  defp code(%{"code" => code}) when is_binary(code), do: code
  defp code(%{"code" => code}) when is_integer(code), do: Integer.to_string(code)
  defp code(_error), do: nil

  # A body that is not JSON, such as a proxy's error page, on one line and at most 300 characters.
  defp excerpt(body) do
    text =
      body
      |> String.chunk(:valid)
      |> Enum.map_join(&if(String.valid?(&1), do: &1, else: "\uFFFD"))
      |> String.split()
      |> Enum.join(" ")

    cond do
      text == "" -> nil
      String.length(text) > 300 -> String.slice(text, 0, 297) <> "..."
      true -> text
    end
  end

  defp status_type(401), do: "authentication_error"
  defp status_type(403), do: "permission_error"
  defp status_type(404), do: "not_found_error"
  defp status_type(429), do: "rate_limit_error"
  defp status_type(status) when status in 400..499, do: "invalid_request_error"
  defp status_type(_status), do: "server_error"

  defp unreachable(reason) do
    detail =
      case reason do
        # Mint's reason holds the header value, which may be a key.
        %Mint.HTTPError{reason: {:invalid_header_value, name, _value}} ->
          "invalid value for header #{name}"

        reason ->
          Exception.message(reason)
      end

    %Error{type: "connection_error", message: "Could not reach the gateway: #{detail}"}
  end

  @doc false
  def resource(%__MODULE__{} = stream) do
    Stream.resource(fn -> claim(stream) end, &next/1, &finish/1)
  end

  defp claim(%__MODULE__{owner: owner, flags: flags} = stream) do
    cond do
      self() != owner ->
        raise ArgumentError, "enumerate the stream in the process that created it"

      :atomics.compare_exchange(flags, @claimed, 0, 1) != :ok ->
        raise ArgumentError, "the stream was already read"

      true ->
        state = %{stream: stream, conn: stream.conn, received: stream.received}
        Map.merge(state, %{buffer: "", data: nil, events: [], ended: false})
    end
  end

  defp next(state), do: if(closed?(state), do: {:halt, state}, else: step(state))

  defp step(%{events: [{:chunk, chunk} | rest]} = state), do: {[chunk], %{state | events: rest}}
  defp step(%{events: [:done | _]} = state), do: {:halt, drain(state, drain_limits(state))}
  defp step(%{events: [{:error, body} | _]} = state), do: fail(state, event_error(body))

  defp step(%{events: []} = state) do
    case await_part(state, state.stream.limits) do
      {:part, part, state} -> next(parse(state, part))
      {:end, state} -> halt_or_raise(state, incomplete())
      {{:failed, reason}, state} -> halt_or_raise(state, failure(state.stream, reason))
    end
  end

  # A stream closed with close/1, here or in another process, ends without an error.
  defp halt_or_raise(state, error),
    do: if(closed?(state), do: {:halt, state}, else: fail(state, error))

  defp fail(state, error), do: raise(struct(error, state.stream.details))

  defp closed?(state), do: :atomics.get(state.stream.flags, @connection) == @closed

  # Reads the rest of the reply after [DONE], for @drain_timeout ms at most,
  # so that a connection read to its end can serve the next call to the gateway.
  defp drain(state, limits) do
    case await_part(state, limits) do
      {:part, _part, state} -> drain(state, limits)
      {:end, state} -> %{state | ended: true}
      {{:failed, _reason}, state} -> state
    end
  end

  defp drain_limits(%{stream: %{limits: {deadline, idle}}}),
    do: {min(deadline, now() + @drain_timeout), idle}

  # Only a reply read to its end gives its connection back, idle from then,
  # unless close/1 got there first.
  defp finish(%{stream: stream, conn: conn} = state) do
    released? = :atomics.compare_exchange(stream.flags, @connection, @open, @released) == :ok

    if released? and state.ended,
      do: Pool.checkin(stream.origin, Mint.HTTP1.put_private(conn, :idle_since, now())),
      else: Mint.HTTP1.close(conn)
  end

  # The next body part, or the end of the body, or why it broke off.
  defp await_part(%{received: [response | rest]} = state, limits) do
    state = %{state | received: rest}

    case response do
      {:data, _ref, part} -> {:part, part, state}
      {:done, _ref} -> {:end, state}
      {:failed, _reason} = failed -> {failed, state}
      _trailers -> await_part(state, limits)
    end
  end

  defp await_part(%{received: []} = state, limits) do
    {conn, received} = recv(state.conn, limits)
    await_part(%{state | conn: conn, received: received}, limits)
  end

  # Each read waits for any bytes, so the idle limit restarts whenever some arrive.
  # Mint returns what it read before a failure along with it, so no byte that arrived is lost.
  defp recv(conn, {deadline, idle}) do
    case Mint.HTTP1.recv(conn, 0, min(remaining(deadline), idle)) do
      {:ok, conn, responses} -> {conn, responses}
      {:error, conn, reason, responses} -> {conn, responses ++ [{:failed, reason}]}
    end
  end

  # Splits only the new part, so a long line is not scanned again as each part arrives.
  defp parse(state, part) do
    {lines, buffer} =
      case :binary.split(part, "\n", [:global]) do
        [partial] ->
          {[], state.buffer <> partial}

        [first | more] ->
          {lines, [partial]} = Enum.split(more, -1)
          {[state.buffer <> first | lines], partial}
      end

    case Enum.reduce_while(lines, {state.data, []}, &line/2) do
      {:over, events} ->
        too_large(state, events)

      {_data, events} when byte_size(buffer) > @event_limit ->
        too_large(state, events)

      {data, events} ->
        %{state | buffer: buffer, data: data, events: Enum.reverse(events)}
    end
  end

  # `data` is the event's data so far, or nil before its first data line.
  defp line(line, {_data, events}) when byte_size(line) > @event_limit,
    do: {:halt, {:over, events}}

  defp line(line, {data, events}) do
    case String.trim_trailing(line, "\r") do
      "" when data == nil -> {:cont, {nil, events}}
      "" -> {:cont, {nil, [event(data) | events]}}
      "data:" <> value -> add_data(data, String.replace_prefix(value, " ", ""), events)
      _comment_or_other_field -> {:cont, {data, events}}
    end
  end

  defp add_data(nil, value, events), do: {:cont, {value, events}}

  defp add_data(data, value, events) when byte_size(data) + 1 + byte_size(value) > @event_limit,
    do: {:halt, {:over, events}}

  defp add_data(data, value, events), do: {:cont, {<<data::binary, ?\n, value::binary>>, events}}

  # Drops what the stream holds, and fails after the events that came before.
  defp too_large(state, events) do
    events = Enum.reverse([{:error, @too_large} | events])
    %{state | buffer: "", data: nil, events: events}
  end

  defp event("[DONE]"), do: :done

  defp event(data) do
    case Jason.decode(data) do
      {:ok, %{"error" => %{} = error}} ->
        {:error, error}

      {:ok, chunk} when is_map(chunk) ->
        {:chunk, chunk}

      _not_an_object ->
        {:error,
         %{"type" => "server_error", "message" => "The gateway sent an event that is not JSON."}}
    end
  end

  defp event_error(error) do
    %Error{
      type: if(is_binary(error["type"]), do: error["type"], else: "model_error"),
      message:
        if(is_binary(error["message"]), do: error["message"], else: "The model stream failed."),
      code: code(error)
    }
  end

  defp failure(stream, %Mint.TransportError{reason: :timeout}), do: timeout_error(stream.limits)
  defp failure(_stream, %Mint.TransportError{reason: :closed}), do: incomplete()

  defp failure(_stream, reason) do
    %Error{
      type: "connection_error",
      message: "The connection to the gateway failed: #{Exception.message(reason)}"
    }
  end

  defp timeout_error({deadline, idle}) do
    if remaining(deadline) > 0 and idle != :infinity,
      do: %Error{type: "timeout", message: "The gateway sent nothing for #{idle} ms."},
      else: timeout_error()
  end

  defp timeout_error, do: %Error{type: "timeout", message: "The request timed out."}

  defp incomplete,
    do: %Error{type: "incomplete_stream", message: "The stream ended before [DONE]."}

  defp remaining(:infinity), do: :infinity
  defp remaining(deadline), do: max(deadline - now(), 0)

  defp now, do: System.monotonic_time(:millisecond)
end

defimpl Enumerable, for: Moss.Inference.ChatCompletionStream do
  def reduce(stream, acc, fun),
    do: Moss.Inference.ChatCompletionStream.resource(stream).(acc, fun)

  def count(_stream), do: {:error, __MODULE__}
  def member?(_stream, _value), do: {:error, __MODULE__}
  def slice(_stream), do: {:error, __MODULE__}
end
