defmodule Moss.Session do
  @moduledoc """
  Local in-session index — index documents in memory during a session and
  query them with no cloud round trips.

  Sessions are opened via `Moss.Client.session/3`, which handles credentials
  and auto-loading from the cloud:

      {:ok, session} = Moss.Client.session(client, "session-abc", model_id: "moss-minilm")

      docs = [%Moss.DocumentInfo{id: "1", text: "hello"}]
      {:ok, {1, 0}} = Moss.Session.add_docs(session, docs)

      {:ok, result} = Moss.Session.query(session, "hello")
      {:ok, push_result} = Moss.Session.push_index(session)

  For `model_id: "custom"`, each document must have `.embedding` set and
  `query/3` requires `embedding: [...]` in opts.

  Call `close/1` when done, so the final usage telemetry is delivered and the
  session's memory freed.
  """

  use GenServer

  alias MossCore.Nif

  @doc false
  def child_spec(opts), do: super(opts)

  # ---------------------------------------------------------------------------
  # Public API
  # ---------------------------------------------------------------------------

  @doc false
  @spec start_link(keyword()) :: GenServer.on_start()
  def start_link(opts) do
    {server_name_opts, opts} = pop_server_name(opts)
    GenServer.start_link(__MODULE__, opts, server_name_opts)
  end

  # Unlinked start. Session creation authenticates eagerly, so init can stop
  # with a cloud error; an unlinked start turns that into {:error, reason}
  # instead of an exit signal that kills a non-trapping caller.
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

  @doc "Number of documents in the session index."
  @spec doc_count(GenServer.server()) :: non_neg_integer()
  def doc_count(pid) do
    GenServer.call(pid, :doc_count)
  end

  @doc "The index name."
  @spec name(GenServer.server()) :: String.t()
  def name(pid) do
    GenServer.call(pid, :name)
  end

  @doc """
  Add documents to the session index.

  For built-in models (`"moss-minilm"`, `"moss-mediumlm"`), embeddings are
  computed automatically in Rust. For `model_id: "custom"`, each document must
  have `.embedding` set.

  Options:
    - `:upsert` (boolean, default true)

  Returns `{:ok, {added, updated}}` or `{:error, reason}`.
  """
  @spec add_docs(GenServer.server(), list(), keyword()) ::
          {:ok, {non_neg_integer(), non_neg_integer()}} | {:error, Moss.Error.t()}
  def add_docs(pid, docs, opts \\ []) do
    upsert = Keyword.get(opts, :upsert, true)
    GenServer.call(pid, {:add_docs, docs, upsert}, :infinity)
  end

  @doc "Delete documents by IDs. Returns the count deleted."
  @spec delete_docs(GenServer.server(), list(String.t())) :: non_neg_integer()
  def delete_docs(pid, doc_ids) do
    GenServer.call(pid, {:delete_docs, doc_ids})
  end

  @doc """
  Get documents from the index.

  Options:
    - `:doc_ids` (list of strings)
  """
  @spec get_docs(GenServer.server(), keyword()) :: list(Moss.DocumentInfo.t())
  def get_docs(pid, opts \\ []) do
    doc_ids = Keyword.get(opts, :doc_ids, nil)
    GenServer.call(pid, {:get_docs, doc_ids})
  end

  @doc """
  Query the session index.

  For built-in models, the query is embedded automatically in Rust. For
  `model_id: "custom"`, pass the query embedding via `embedding: [...]`.

  Options:
    - `:top_k` (integer, default 5)
    - `:alpha` (float, default 0.8)
    - `:filter` (map)
    - `:embedding` (list of floats, required for `model_id: "custom"`)

  Returns `{:ok, Moss.SearchResult.t()}` or `{:error, reason}`.
  """
  @spec query(GenServer.server(), String.t(), keyword()) ::
          {:ok, Moss.SearchResult.t()} | {:error, Moss.Error.t()}
  def query(pid, query_text, opts \\ []) do
    top_k = Keyword.get(opts, :top_k, 5)
    alpha = Keyword.get(opts, :alpha, 0.8)
    filter = Keyword.get(opts, :filter, nil)
    embedding = Keyword.get(opts, :embedding, nil)
    GenServer.call(pid, {:query, query_text, embedding, top_k, alpha, filter}, :infinity)
  end

  @doc false
  @spec load_model(GenServer.server()) :: {:ok, :ok} | {:error, Moss.Error.t()}
  def load_model(pid) do
    GenServer.call(pid, :load_model, :infinity)
  end

  @doc """
  The embedding model the session uses, or `"custom"`.

  A load moves the session to the loaded model, so after a
  custom-model load `add_docs/3` and `query/3` need embeddings.
  """
  @spec model_id(GenServer.server()) :: String.t()
  def model_id(pid) do
    GenServer.call(pid, :model_id)
  end

  @doc """
  Load an existing cloud index into this session.

  The index replaces this session's documents and model, so `add_docs/3` and
  `query/3` need embeddings after a custom-model index loads.

  Returns `{:ok, doc_count}` or `{:error, reason}`.
  """
  @spec load_index(GenServer.server(), String.t()) ::
          {:ok, non_neg_integer()} | {:error, Moss.Error.t()}
  def load_index(pid, index_name) do
    GenServer.call(pid, {:load_index, index_name}, :infinity)
  end

  @doc """
  Push the local session index to the cloud.

  Returns `{:ok, Moss.PushIndexResult.t()}` or `{:error, reason}`.
  """
  @spec push_index(GenServer.server()) ::
          {:ok, Moss.PushIndexResult.t()} | {:error, Moss.Error.t()}
  def push_index(pid) do
    GenServer.call(pid, :push_index, :infinity)
  end

  @doc """
  Save the session under `<cache_path>/<name>/`, so a later session with the
  same name can restore it with `load_from_disk/3`. Open that session with
  `auto_load_on_init: false` so the restore downloads no index.

  Without `cache_path` the snapshot goes in `sessions/<project id>/` under the client's
  `:cache_path`, else under the `MOSS_SESSION_CACHE_PATH` environment variable, which
  only session snapshots read, else under `moss` in the default cache directory
  (`~/.cache` on macOS and Linux, `%LOCALAPPDATA%` on Windows). A relative
  `cache_path` resolves against the current working directory, and `~` is not expanded.
  The core reads `MOSS_SESSION_CACHE_PATH` from the environment the VM started with, so
  `System.put_env/2` does not change it; set the client's `:cache_path` instead.

  A failed or interrupted save leaves the last saved snapshot loadable. For a
  built-in model the snapshot records the model id and the exact model artifact.

  Returns `:ok` or `{:error, reason}`.
  """
  @spec save_to_disk(GenServer.server(), String.t() | nil) :: :ok | {:error, Moss.Error.t()}
  def save_to_disk(pid, cache_path \\ nil) do
    GenServer.call(pid, {:save_to_disk, cache_path}, :infinity)
  end

  @doc """
  Restore a session saved by `save_to_disk/2` from `<cache_path>/<name>/`.
  Without `cache_path`, or with only options, it reads the directory that
  `save_to_disk/2` picks when called without one.

  The snapshot replaces this session's documents and model, so `add_docs/3` and
  `query/3` need embeddings after loading a custom-model snapshot. A missing or
  damaged snapshot returns `{:error, %Moss.Error{code: :deserialization}}` and
  leaves the session as it was.

  A snapshot saved for a built-in model by an older core carries no model
  artifact identity, so the core can only restore it as a custom-model session.
  With `rebuild_legacy: true` (the default), a session opened with the same
  built-in model rebuilds such a snapshot instead: the stored documents are
  re-embedded with the current model and the upgraded snapshot is saved back, in
  one call, so the rebuild happens once per device. It needs the model, so the
  cloud must be reachable. When the model cannot be loaded the call returns
  `{:error, %Moss.Error{code: :model_unavailable}}` and changes nothing, so retry
  later instead of discarding the snapshot. Custom-model sessions and snapshots of
  another model load without a rebuild.

  Options:
    - `:rebuild_legacy` (boolean, default true)

  Returns `{:ok, doc_count}` or `{:error, reason}`.
  """
  @spec load_from_disk(GenServer.server(), String.t() | nil | keyword(), keyword()) ::
          {:ok, non_neg_integer()} | {:error, Moss.Error.t()}
  def load_from_disk(pid, cache_path \\ nil, opts \\ [])

  def load_from_disk(pid, opts, []) when opts == [] or (is_list(opts) and is_tuple(hd(opts))),
    do: load_from_disk(pid, nil, opts)

  def load_from_disk(pid, cache_path, opts) do
    rebuild_legacy = Keyword.get(opts, :rebuild_legacy, true)
    GenServer.call(pid, {:load_from_disk, cache_path, rebuild_legacy}, :infinity)
  end

  @doc """
  Close the session: send its final usage telemetry and stop its process.

  Waits until the telemetry is delivered or 2 seconds pass. Closing a session that
  already stopped returns `:ok`. A supervisor shutting the session down, or the exit
  of the process that started it with `start_link/1`, closes it the same way.
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
    name        = Keyword.fetch!(opts, :name)
    model_id    = Keyword.fetch!(opts, :model_id)
    project_id  = Keyword.fetch!(opts, :project_id)
    project_key = Keyword.fetch!(opts, :project_key)
    client_id   = Keyword.get(opts, :client_id, nil)
    device_id   = Keyword.get(opts, :device_id, nil)
    moss_device_id = Keyword.get(opts, :moss_device_id, nil)
    cache_path  = Keyword.get(opts, :cache_path, nil)

    case Nif.session_new(name, model_id, project_id, project_key, client_id) do
      {:ok, ref} ->
        if device_id || moss_device_id,
          do: Nif.session_set_identity(ref, device_id, nil, moss_device_id)
        {:ok, %{ref: ref, cache_path: cache_path}}

      {:error, reason} ->
        {:stop, reason}
    end
  end

  @impl true
  def handle_call(:doc_count, _from, state) do
    {:reply, Nif.session_doc_count(state.ref), state}
  end

  def handle_call(:name, _from, state) do
    {:reply, Nif.session_name(state.ref), state}
  end

  def handle_call(:model_id, _from, state), do: {:reply, Nif.session_model_id(state.ref), state}

  def handle_call({:add_docs, docs, upsert}, _from, state) do
    reply =
      if custom?(state) do
        case extract_embeddings(docs) do
          {:ok, embeddings} -> Nif.session_add_docs(state.ref, docs, embeddings, upsert)
          {:error, _} = err -> err
        end
      else
        Nif.session_add_docs_text(state.ref, docs, upsert)
      end

    {:reply, reply, state}
  end

  def handle_call({:delete_docs, doc_ids}, _from, state) do
    {:reply, Nif.session_delete_docs(state.ref, doc_ids), state}
  end

  def handle_call({:get_docs, doc_ids}, _from, state) do
    {:reply, Nif.session_get_docs(state.ref, doc_ids), state}
  end

  def handle_call({:query, query_text, nil, top_k, alpha, filter}, _from, state) do
    reply =
      if custom?(state) do
        {:error,
         Moss.Error.invalid_argument(
           ~s(model_id: "custom" requires a query embedding. Pass embedding: [...] in query opts.)
         )}
      else
        Nif.session_query_text(state.ref, query_text, top_k, alpha, filter)
      end

    {:reply, reply, state}
  end

  def handle_call({:query, query_text, embedding, top_k, alpha, filter}, _from, state) do
    {:reply, Nif.session_query(state.ref, query_text, top_k, embedding, alpha, filter), state}
  end

  # A custom-model session has no model to load.
  def handle_call(:load_model, _from, state) do
    reply = if custom?(state), do: {:ok, :ok}, else: Nif.session_load_model(state.ref)
    {:reply, reply, state}
  end

  def handle_call({:load_index, index_name}, _from, state) do
    {:reply, Nif.session_load_index(state.ref, index_name), state}
  end

  def handle_call({:load_from_disk, cache_path, rebuild_legacy}, _from, state) do
    reply = Nif.session_load_from_disk(state.ref, cache_path, state.cache_path, rebuild_legacy)
    {:reply, reply, state}
  end

  def handle_call(:push_index, _from, state) do
    {:reply, Nif.session_push_index(state.ref), state}
  end

  def handle_call({:save_to_disk, cache_path}, _from, state) do
    reply =
      case Nif.session_save_to_disk(state.ref, cache_path, state.cache_path) do
        {:ok, :ok} -> :ok
        {:error, _} = err -> err
      end

    {:reply, reply, state}
  end

  @impl true
  def handle_info({:EXIT, _pid, :normal}, state), do: {:noreply, state}
  def handle_info({:EXIT, _pid, reason}, state), do: {:stop, reason, state}

  @impl true
  def terminate(_reason, state) do
    Nif.session_close(state.ref)
  end

  # ---------------------------------------------------------------------------
  # Private helpers
  # ---------------------------------------------------------------------------

  # A load can move the core to another model, so each call reads it from the core.
  defp custom?(state), do: Nif.session_model_id(state.ref) == "custom"

  defp extract_embeddings(docs) do
    missing = docs |> Enum.filter(&is_nil(&1.embedding)) |> Enum.map(& &1.id)

    if missing == [] do
      {:ok, Enum.map(docs, & &1.embedding)}
    else
      {:error,
       Moss.Error.invalid_argument(
         ~s(Documents missing .embedding for model_id: "custom": #{inspect(missing)}. ) <>
           "Set embedding on each %Moss.DocumentInfo{}."
       )}
    end
  end
end
