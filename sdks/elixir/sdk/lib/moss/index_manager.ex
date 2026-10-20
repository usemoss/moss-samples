defmodule Moss.IndexManager do
  @moduledoc false

  use GenServer

  alias MossCore.Nif

  # ---------------------------------------------------------------------------
  # Public API
  # ---------------------------------------------------------------------------

  @doc """
  Start an IndexManager GenServer.

  Required options:
    - `:project_id`
    - `:project_key`

  Optional:
    - `:server_name` — GenServer name registration
  """
  @spec start_link(keyword()) :: GenServer.on_start()
  def start_link(opts) do
    {server_name_opts, opts} = pop_server_name(opts)
    GenServer.start_link(__MODULE__, opts, server_name_opts)
  end

  # Unlinked start for a caller that links afterwards, so the caller's normal
  # exit leaves the manager running, as it does without trapped exits.
  @doc false
  @spec start(keyword()) :: GenServer.on_start()
  def start(opts) do
    {server_name_opts, opts} = pop_server_name(opts)
    GenServer.start(__MODULE__, opts, server_name_opts)
  end

  defp pop_server_name(opts) do
    case Keyword.pop(opts, :server_name) do
      {nil, rest} -> {[], rest}
      {name, rest} -> {[name: name], rest}
    end
  end

  @doc """
  Load a cloud index into memory.

  The core warms a built-in embedding model as part of the load.
  With a `:cache_path` snapshot on disk and the cloud unreachable, the load
  serves that snapshot and returns `{:ok, info}` even when the model cannot open.

  Options:
    - `:auto_refresh` (boolean, default false)
    - `:polling_interval` (integer seconds, default 600, minimum 1; 0 uses
      the default)
    - `:cache_path` (directory for the on-disk index cache; defaults to the
      manager's `:cache_path`)

  Returns `{:ok, Moss.IndexInfo.t()}` or `{:error, reason}`.
  """
  @spec load_index(GenServer.server(), String.t(), keyword()) ::
          {:ok, Moss.IndexInfo.t()} | {:error, Moss.Error.t()}
  def load_index(pid, index_name, opts \\ []) do
    auto_refresh = Keyword.get(opts, :auto_refresh, false)
    polling_interval = Keyword.get(opts, :polling_interval, 600)
    cache_path = Moss.Client.normalize_cache_path(Keyword.get(opts, :cache_path, nil))

    GenServer.call(
      pid,
      {:load_index, index_name, auto_refresh, polling_interval, cache_path},
      :infinity
    )
  end

  @doc "Unload an index from memory."
  @spec unload_index(GenServer.server(), String.t()) :: {:ok, :ok} | {:error, Moss.Error.t()}
  def unload_index(pid, index_name) do
    GenServer.call(pid, {:unload_index, index_name}, :infinity)
  end

  @doc "Check if an index is loaded."
  @spec has_index(GenServer.server(), String.t()) :: boolean()
  def has_index(pid, index_name) do
    GenServer.call(pid, {:has_index, index_name}, :infinity)
  end

  @doc false
  @spec device_identity(GenServer.server()) :: {String.t() | nil, String.t() | nil}
  def device_identity(pid) do
    GenServer.call(pid, :device_identity, :infinity)
  end

  @doc """
  Query a loaded index.

  For built-in models, the query is embedded automatically in Rust. For indexes
  created with `model_id: "custom"`, pass the query embedding via `embedding: [...]`.

  Options:
    - `:top_k` (integer, default 5)
    - `:alpha` (float, default 0.8)
    - `:filter` (map)
    - `:embedding` (list of floats, required for `model_id: "custom"`)

  Returns `{:ok, Moss.SearchResult.t()}` or `{:error, reason}`.
  """
  @spec query(GenServer.server(), String.t(), String.t(), keyword()) ::
          {:ok, Moss.SearchResult.t()} | {:error, Moss.Error.t()}
  def query(pid, index_name, query_text, opts \\ []) do
    {top_k, alpha, filter, embedding} = query_opts(opts)

    GenServer.call(
      pid,
      {:query, index_name, query_text, embedding, top_k, alpha, filter},
      :infinity
    )
  end

  @doc """
  Bulk-load many indexes into memory.

  The core warms each loaded index's embedding model during load, so every name
  reported in `loaded` is already query-ready; no separate `load_query_model`
  pass is needed.

  Options:
    - `:auto_refresh` (boolean, default false)
    - `:polling_interval` (integer seconds, default 600, minimum 1; 0 uses
      the default)

  Returns `{:ok, Moss.LoadIndexesResult.t()}`.
  """
  @spec load_indexes(GenServer.server(), [String.t()], keyword()) ::
          {:ok, Moss.LoadIndexesResult.t()}
  def load_indexes(pid, index_names, opts \\ []) do
    auto_refresh = Keyword.get(opts, :auto_refresh, false)
    polling_interval = Keyword.get(opts, :polling_interval, 600)
    GenServer.call(pid, {:load_indexes, index_names, auto_refresh, polling_interval}, :infinity)
  end

  @doc "Bulk-unload indexes from memory. Idempotent for names that are not loaded."
  @spec unload_indexes(GenServer.server(), [String.t()]) :: :ok
  def unload_indexes(pid, index_names) do
    GenServer.call(pid, {:unload_indexes, index_names}, :infinity)
  end

  @doc """
  Search several loaded indexes in one call and get the global top-k.

  Options:
    - `:top_k` (integer, default 10)
    - `:alpha` (float, default 0.8)
    - `:filter` (map)
    - `:embedding` (list of floats, required for `model_id: "custom"` unless `alpha: 0.0`)

  Returns `{:ok, Moss.SearchResult.t()}` or `{:error, reason}`.
  """
  @spec query_multi_index(GenServer.server(), [String.t()], String.t(), keyword()) ::
          {:ok, Moss.SearchResult.t()} | {:error, Moss.Error.t()}
  def query_multi_index(pid, index_names, query_text, opts \\ [])

  def query_multi_index(_pid, [], _query_text, _opts) do
    {:error, Moss.Error.invalid_argument("query_multi_index requires at least one index name")}
  end

  def query_multi_index(pid, index_names, query_text, opts) do
    {top_k, alpha, filter, embedding} = query_opts(opts, 10)

    GenServer.call(
      pid,
      {:query_multi_index, index_names, query_text, embedding, top_k, alpha, filter},
      :infinity
    )
  end

  @doc false
  @spec load_query_model(GenServer.server(), String.t()) :: {:ok, :ok} | {:error, Moss.Error.t()}
  def load_query_model(pid, index_name) do
    GenServer.call(pid, {:load_query_model, index_name}, :infinity)
  end

  @doc "Install the cloud's snapshot of a loaded index when it is newer. A snapshot no newer than the loaded one, with the same model, downloads nothing and returns `was_updated: false`."
  @spec refresh_index(GenServer.server(), String.t()) ::
          {:ok, Moss.RefreshResult.t()} | {:error, Moss.Error.t()}
  def refresh_index(pid, index_name) do
    GenServer.call(pid, {:refresh_index, index_name}, :infinity)
  end

  @doc "Get metadata for a loaded index."
  @spec get_index_info(GenServer.server(), String.t()) ::
          {:ok, Moss.IndexInfo.t()} | {:error, Moss.Error.t()}
  def get_index_info(pid, index_name) do
    GenServer.call(pid, {:get_index_info, index_name}, :infinity)
  end

  @doc """
  Close the manager: send its final usage telemetry, unload every index and stop its process.

  Waits until the telemetry is delivered or 2 seconds pass. Closing a manager that
  already stopped returns `:ok`. A supervisor shutting the manager down, or the exit
  of the process that started it, closes it the same way.
  """
  @spec close(GenServer.server()) :: :ok
  def close(pid) do
    GenServer.stop(pid, :normal, :infinity)
  catch
    :exit, {:noproc, _} -> :ok
    :exit, {:normal, _} -> :ok
    :exit, {:shutdown, _} -> :ok
    :exit, {{:shutdown, _}, _} -> :ok
  end

  # ---------------------------------------------------------------------------
  # GenServer callbacks
  # ---------------------------------------------------------------------------

  @impl true
  def init(opts) do
    Process.flag(:trap_exit, true)
    project_id = Keyword.fetch!(opts, :project_id)
    project_key = Keyword.fetch!(opts, :project_key)
    client_id = Keyword.get(opts, :client_id, nil)
    device_id = Keyword.get(opts, :device_id, nil)
    cache_path = Moss.Client.normalize_cache_path(Keyword.get(opts, :cache_path, nil))

    case Nif.manager_new(project_id, project_key, nil, client_id) do
      {:ok, ref} ->
        if device_id, do: Nif.manager_set_device_id(ref, device_id)
        {:ok, %{ref: ref, cache_path: cache_path}}

      {:error, reason} ->
        {:stop, reason}
    end
  end

  @impl true
  def handle_call(
        {:load_index, index_name, auto_refresh, polling_interval, cache_path},
        _from,
        state
      ) do
    reply =
      Nif.manager_load_index(
        state.ref,
        index_name,
        auto_refresh,
        polling_interval,
        cache_path || state.cache_path
      )

    {:reply, reply, state}
  end

  def handle_call({:unload_index, index_name}, _from, state) do
    {:reply, Nif.manager_unload_index(state.ref, index_name), state}
  end

  def handle_call({:has_index, index_name}, _from, state) do
    {:reply, Nif.manager_has_index(state.ref, index_name), state}
  end

  def handle_call(:device_identity, _from, state) do
    {:reply, Nif.manager_device_identity(state.ref), state}
  end

  def handle_call({:query, index_name, query_text, nil, top_k, alpha, filter}, _from, state) do
    {:reply, Nif.manager_query_text(state.ref, index_name, query_text, top_k, alpha, filter),
     state}
  end

  def handle_call({:query, index_name, query_text, embedding, top_k, alpha, filter}, _from, state) do
    {:reply,
     Nif.manager_query(state.ref, index_name, query_text, embedding, top_k, alpha, filter),
     state}
  end

  def handle_call({:load_indexes, index_names, auto_refresh, polling_interval}, _from, state) do
    {:reply,
     {:ok, Nif.manager_load_indexes(state.ref, index_names, auto_refresh, polling_interval)},
     state}
  end

  def handle_call({:unload_indexes, index_names}, _from, state) do
    {:reply, Nif.manager_unload_indexes(state.ref, index_names), state}
  end

  def handle_call(
        {:query_multi_index, index_names, query_text, nil, top_k, alpha, filter},
        _from,
        state
      ) do
    {:reply,
     Nif.manager_query_multi_index_text(state.ref, index_names, query_text, top_k, alpha, filter),
     state}
  end

  def handle_call(
        {:query_multi_index, index_names, query_text, embedding, top_k, alpha, filter},
        _from,
        state
      ) do
    {:reply,
     Nif.manager_query_multi_index(
       state.ref,
       index_names,
       query_text,
       embedding,
       top_k,
       alpha,
       filter
     ), state}
  end

  def handle_call({:load_query_model, index_name}, _from, state) do
    {:reply, Nif.manager_load_query_model(state.ref, index_name), state}
  end

  def handle_call({:refresh_index, index_name}, _from, state) do
    {:reply, Nif.manager_refresh_index(state.ref, index_name), state}
  end

  def handle_call({:get_index_info, index_name}, _from, state) do
    {:reply, Nif.manager_get_index_info(state.ref, index_name), state}
  end

  @impl true
  def handle_info({:EXIT, _pid, :normal}, state), do: {:noreply, state}
  def handle_info({:EXIT, _pid, reason}, state), do: {:stop, reason, state}

  @impl true
  def terminate(_reason, state) do
    Nif.manager_close(state.ref)
  end

  # ---------------------------------------------------------------------------
  # Private helpers
  # ---------------------------------------------------------------------------

  defp query_opts(opts, default_top_k \\ 5) do
    top_k = Keyword.get(opts, :top_k, default_top_k)
    alpha = Keyword.get(opts, :alpha, 0.8)
    filter = Keyword.get(opts, :filter, nil)
    embedding = Keyword.get(opts, :embedding, nil)
    {top_k, alpha, filter, embedding}
  end
end
