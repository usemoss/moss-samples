defmodule Moss.Inference.Pool do
  @moduledoc false

  # Idle connections to inference gateways, kept for the next call to the same host.
  #
  # A call owns its connection until the reply ends, so the pool holds only idle ones,
  # and a call whose process dies takes its socket with it. A connection comes back when
  # its reply was read to its end, or unused when it reached its call too late, as a :pending
  # entry until the caller hands the socket over, and each host keeps at most @max_idle of them.
  #
  # An idle socket is active, so a close or stray bytes
  # from the gateway reach the pool as a message, and it drops them.
  # Each connection closes @idle_time ms after its reply ended, as its
  # private :idle_since records, so one that comes back unused gets no more time.
  #
  # The pool traps exits. A TCP socket that changes owner is linked to both for a moment,
  # and a caller killed then takes the socket down, which must not take the pool with it.

  use GenServer

  # Under the 5 s keep-alive of common HTTP servers, so the client closes first.
  @idle_time 4_000
  @max_idle 100

  @socket_tags [:tcp, :tcp_closed, :tcp_error, :ssl, :ssl_closed, :ssl_error]

  # The flag a checkout shares between its caller and the pool.
  # The pool takes the checkout, and marks a hand-over done if the caller still waits.
  # The caller leaves before the pool takes it, or while the pool hands a connection over.
  @open 0
  @taken 1
  @left 2
  @handed 3

  @type origin :: {:http | :https, String.t(), :inet.port_number()}

  @spec start_link(term()) :: GenServer.on_start()
  def start_link(_arg), do: GenServer.start_link(__MODULE__, :ok, name: __MODULE__)

  @doc """
  An idle connection to `origin`, now owned by the caller, or nil.

  The caller waits `wait` ms for the pool to take the checkout,
  then as long again, but not past the monotonic `deadline`, for the hand-over.
  A caller that left is handed nothing, and a connection handed to it after it left is closed.
  """
  @spec checkout(origin(), timeout(), integer() | :infinity) :: Mint.HTTP1.t() | nil
  def checkout(origin, wait, deadline) do
    case GenServer.whereis(__MODULE__) do
      nil -> nil
      pool -> await(pool, origin, wait, deadline)
    end
  end

  defp await(pool, origin, wait, deadline) do
    flag = :atomics.new(1, [])
    request = :gen_server.send_request(pool, {:checkout, origin, flag})

    with :timeout <- :gen_server.wait_response(request, wait),
         :taken <- leave(request, flag, @open),
         :timeout <- :gen_server.wait_response(request, min(wait, remaining(deadline))),
         :taken <- leave(request, flag, @taken) do
      # The pool replied before it marked the hand-over done, so the reply is here.
      reply(:gen_server.receive_response(request, 0))
    else
      response -> reply(response)
    end
  end

  # Leaves a checkout still in `state`, dropping the request and any reply to it.
  defp leave(request, flag, state) do
    if swap(flag, state, @left) do
      :gen_server.receive_response(request, 0)
      :left
    else
      :taken
    end
  end

  defp reply({:reply, conn}), do: conn
  defp reply(_left_or_no_pool), do: nil

  defp swap(flag, from, to), do: :atomics.compare_exchange(flag, 1, from, to) == :ok

  defp remaining(:infinity), do: :infinity
  defp remaining(deadline), do: max(deadline - now(), 0)

  defp now, do: System.monotonic_time(:millisecond)

  @doc """
  Hands back an idle connection, such as one whose reply was read to its end, or closes it.

  `conn` holds the monotonic ms its reply ended as the private `:idle_since`.
  The pool learns of the connection before it owns the socket, so a caller
  that dies between the two leaves an entry that expires, not a lost socket.
  """
  @spec checkin(origin(), Mint.HTTP1.t()) :: :ok
  def checkin(origin, conn) do
    with pool when is_pid(pool) <- GenServer.whereis(__MODULE__),
         true <- Mint.HTTP1.open?(conn) and Mint.HTTP1.open_request_count(conn) == 0 do
      ref = make_ref()
      GenServer.cast(pool, {:checkin, origin, ref, conn})

      case Mint.HTTP1.controlling_process(conn, pool) do
        {:ok, _conn} -> GenServer.cast(pool, {:owned, origin, ref})
        {:error, _reason} -> Mint.HTTP1.close(conn)
      end
    else
      _closed_or_no_pool -> Mint.HTTP1.close(conn)
    end

    :ok
  end

  @impl true
  def init(:ok) do
    Process.flag(:trap_exit, true)
    {:ok, %{}}
  end

  # A caller that died or left takes nothing, and the idle connections stay.
  # One that left during the hand-over never reads the reply, so its connection closes.
  @impl true
  def handle_call({:checkout, origin, flag}, {caller, _tag} = from, idle) do
    if Process.alive?(caller) and swap(flag, @open, @taken) do
      {conn, rest} = take(Map.get(idle, origin, []), caller, flag)
      GenServer.reply(from, conn)
      if conn != nil and not swap(flag, @taken, @handed), do: close(conn)
      {:noreply, put(idle, origin, rest)}
    else
      {:reply, nil, idle}
    end
  end

  @impl true
  def handle_cast({:checkin, origin, ref, conn}, idle) do
    conns = Map.get(idle, origin, [])
    left = Mint.HTTP1.get_private(conn, :idle_since) + @idle_time - now()

    if length(conns) < @max_idle and left > 0 do
      Process.send_after(self(), {:expire, origin, ref}, left)
      {:noreply, Map.put(idle, origin, [{ref, conn, :pending} | conns])}
    else
      close(conn)
      {:noreply, idle}
    end
  end

  def handle_cast({:owned, origin, ref}, idle) do
    conns = Map.get(idle, origin, [])

    with {^ref, conn, :pending} <- List.keyfind(conns, ref, 0),
         {:ok, conn} <- Mint.HTTP1.set_mode(conn, :active) do
      {:noreply, Map.put(idle, origin, List.keyreplace(conns, ref, 0, {ref, conn, :owned}))}
    else
      nil -> {:noreply, idle}
      {:error, _reason} -> {:noreply, drop(idle, origin, &(elem(&1, 0) == ref))}
    end
  end

  @impl true
  def handle_info({:expire, origin, ref}, idle),
    do: {:noreply, drop(idle, origin, &(elem(&1, 0) == ref))}

  # A socket the pool is linked to closed, or went down with a caller that was handing it over.
  def handle_info({:EXIT, socket, _reason}, idle), do: {:noreply, drop_socket(idle, socket)}

  def handle_info(message, idle)
      when tuple_size(message) in [2, 3] and elem(message, 0) in @socket_tags,
      do: {:noreply, drop_socket(idle, elem(message, 1))}

  def handle_info(_message, idle), do: {:noreply, idle}

  # The newest owned connection the gateway has not closed, handed to `caller`.
  # A caller that died or left meanwhile leaves the other connections where they are.
  defp take(conns, caller, flag) do
    case Enum.split_while(conns, &(elem(&1, 2) == :pending)) do
      {pending, []} ->
        {nil, pending}

      {pending, [{_ref, conn, :owned} | rest]} ->
        case hand_over(conn, caller) do
          {:ok, conn} ->
            {conn, pending ++ rest}

          :closed ->
            close(conn)

            if Process.alive?(caller) and :atomics.get(flag, 1) == @taken,
              do: take(pending ++ rest, caller, flag),
              else: {nil, pending ++ rest}
        end
    end
  end

  defp hand_over(conn, caller) do
    with {:ok, conn} <- Mint.HTTP1.set_mode(conn, :passive),
         :quiet <- quiet(Mint.HTTP1.get_socket(conn)),
         {:ok, conn} <- Mint.HTTP1.controlling_process(conn, caller) do
      {:ok, conn}
    else
      _closed -> :closed
    end
  end

  # A message the socket sent before it went passive means a close or stray bytes.
  defp quiet(socket) do
    receive do
      {tag, ^socket} when tag in @socket_tags -> :closed
      {tag, ^socket, _data_or_reason} when tag in @socket_tags -> :closed
    after
      0 -> :quiet
    end
  end

  defp drop_socket(idle, socket) do
    gone? = fn {_ref, conn, _state} -> Mint.HTTP1.get_socket(conn) == socket end
    Enum.reduce(Map.keys(idle), idle, &drop(&2, &1, gone?))
  end

  defp drop(idle, origin, match?) do
    {dropped, kept} = idle |> Map.get(origin, []) |> Enum.split_with(match?)
    Enum.each(dropped, &close(elem(&1, 1)))
    put(idle, origin, kept)
  end

  defp put(idle, origin, []), do: Map.delete(idle, origin)
  defp put(idle, origin, conns), do: Map.put(idle, origin, conns)

  # Closing a TLS socket can wait on the peer, so it runs outside the pool.
  defp close(conn), do: spawn(fn -> Mint.HTTP1.close(conn) end)
end
