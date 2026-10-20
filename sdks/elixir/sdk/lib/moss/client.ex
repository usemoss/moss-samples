defmodule Moss.Client do
  @moduledoc """
  High-level entry point for the moss Elixir SDK.

  Counterpart to `MossClient` in the Python SDK.

  Example:

      {:ok, client} = Moss.Client.new("project-id", "project-key")

      # Cloud CRUD
      {:ok, result} = Moss.Client.create_index(client, "my-index", docs)
      {:ok, info}   = Moss.Client.get_index(client, "my-index")

      # Load and query a cloud index locally
      {:ok, _}       = Moss.Client.load_index(client, "faq-index")
      {:ok, results} = Moss.Client.query(client, "faq-index", "cancel")

      # Search several loaded indexes in one call
      {:ok, _}       = Moss.Client.load_indexes(client, ["a", "b"])
      {:ok, results} = Moss.Client.query_multi_index(client, ["a", "b"], "query")

      # Session workflow with built-in embeddings
      {:ok, session} = Moss.Client.session(client, "session-abc")
      {:ok, {2, 0}}  = Moss.Session.add_docs(session, docs)
      {:ok, result}  = Moss.Session.query(session, "billing issue")
      {:ok, _}       = Moss.Session.push_index(session)

      # Custom models still use explicit embeddings
      {:ok, custom_session} = Moss.Client.session(client, "custom-session", model_id: "custom")
      {:ok, {1, 0}} = Moss.Session.add_docs(custom_session, docs)
      {:ok, custom_result} = Moss.Session.query(custom_session, "billing issue", embedding: my_vec)
  """

  @default_model_id "moss-minilm"

  defstruct [:project_id, :project_key, :client_id, :manage_ref, :manager_pid, :cache_path]

  @type t :: %__MODULE__{
          project_id: String.t(),
          project_key: String.t(),
          client_id: String.t(),
          manage_ref: reference(),
          manager_pid: pid(),
          cache_path: String.t() | nil
        }

  @doc """
  Create a new Moss.Client.

  The index API URL is resolved from the `MOSS_INDEX_URL` environment variable
  (falls back to the default cloud endpoint). No URL option is needed.

  Options:
    - `:cache_path` (directory for the on-disk index cache used by `load_index/3`;
      `<cache_path>/.moss-device-id` is created when missing and adopted as the device id;
      sessions from this client save to `<cache_path>/sessions/<project id>/` by default)
  """
  @spec new(String.t(), String.t(), keyword()) :: {:ok, t()} | {:error, Moss.Error.t()}
  def new(project_id, project_key, opts \\ []) do
    client_id = Uniq.UUID.uuid4()
    cache_path = normalize_cache_path(Keyword.get(opts, :cache_path, nil))

    with {:ok, ref} <- Moss.ManageClient.new(project_id, project_key,
                         client_id: client_id),
         {:ok, pid} <- Moss.IndexManager.start(
                         project_id: project_id,
                         project_key: project_key,
                         client_id: client_id,
                         cache_path: cache_path
                       ) do
      Process.link(pid)
      {:ok,
       %__MODULE__{
         project_id: project_id,
         project_key: project_key,
         client_id: client_id,
         manage_ref: ref,
         manager_pid: pid,
         cache_path: cache_path
       }}
    end
  end

  # ---------------------------------------------------------------------------
  # Cloud CRUD (delegates to Moss.ManageClient)
  # ---------------------------------------------------------------------------

  @doc "Create a cloud index with initial documents."
  @spec create_index(t(), String.t(), list(Moss.DocumentInfo.t()), String.t()) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def create_index(%__MODULE__{manage_ref: ref}, name, docs, model_id \\ @default_model_id) do
    Moss.ManageClient.create_index(ref, name, docs, model_id)
  end

  @doc """
  Add documents to an existing cloud index.

  Options:
    - `:upsert` (boolean, default nil — use server default)
  """
  @spec add_docs(t(), String.t(), list(Moss.DocumentInfo.t()), keyword()) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def add_docs(%__MODULE__{manage_ref: ref}, name, docs, opts \\ []) do
    Moss.ManageClient.add_docs(ref, name, docs, opts)
  end

  @doc "Delete documents by IDs from a cloud index."
  @spec delete_docs(t(), String.t(), list(String.t())) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def delete_docs(%__MODULE__{manage_ref: ref}, name, doc_ids) do
    Moss.ManageClient.delete_docs(ref, name, doc_ids)
  end

  @doc """
  Create an index from raw files via the server-side parse pipeline.

  Each file in `files` is a map with all three keys required:
    - `:path` — filesystem path
    - `:name` — filename sent to the server
    - `:content_type` — MIME type

  `model_id` defaults to "moss-minilm". Must be a built-in model.
  "custom" is not supported because the parse pipeline generates embeddings server-side.

  At most 20 files per call.

  `parse_options` is an optional map controlling extraction. Omitted keys use
  the server defaults:

    - `:ocr_mode`: `"auto_ocr"` or `"full_ocr"`. Use `"full_ocr"` for scanned
      documents with no text layer.
    - `:segmentation_method`: `"smart_layout_detection"` or `"page_by_page"`
    - `:use_high_resolution`: boolean, slower but better on dense tables
    - `:merge_tables`: boolean, join tables split across a page break
    - `:chunk_size`: integer, target length of each chunk in characters,
      200 to 2000 (default 1200)
    - `:chunk_overlap`: integer, characters shared by consecutive chunks,
      0 to half of `:chunk_size` (default 200, capped at half of `:chunk_size`)

  Supported content types: `"application/pdf"` and the DOCX MIME
  `"application/vnd.openxmlformats-officedocument.wordprocessingml.document"`.

  Example:

      {:ok, result} = Moss.Client.create_index_from_files(
        client,
        "my-index",
        [
          %{
            name: "report.pdf",
            content_type: "application/pdf",
            path: "/docs/report.pdf"
          },
          %{
            name: "manual.docx",
            content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            path: "/docs/manual.docx"
          }
        ],
        "moss-minilm",
        %{ocr_mode: "full_ocr"}
      )
  """
  @spec create_index_from_files(
          t(),
          String.t(),
          list(map()),
          String.t(),
          map() | nil
        ) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def create_index_from_files(
        %__MODULE__{manage_ref: ref},
        name,
        files,
        model_id \\ @default_model_id,
        parse_options \\ nil
      ) do
    Moss.ManageClient.create_index_from_files(ref, name, files, model_id, parse_options)
  end

  @doc "Poll the status of an async job."
  @spec get_job_status(t(), String.t()) ::
          {:ok, Moss.JobStatusResponse.t()} | {:error, Moss.Error.t()}
  def get_job_status(%__MODULE__{manage_ref: ref}, job_id) do
    Moss.ManageClient.get_job_status(ref, job_id)
  end

  @doc "Get metadata for a cloud index."
  @spec get_index(t(), String.t()) ::
          {:ok, Moss.IndexInfo.t()} | {:error, Moss.Error.t()}
  def get_index(%__MODULE__{manage_ref: ref}, name) do
    Moss.ManageClient.get_index(ref, name)
  end

  @doc "List all cloud indexes for this project."
  @spec list_indexes(t()) ::
          {:ok, list(Moss.IndexInfo.t())} | {:error, Moss.Error.t()}
  def list_indexes(%__MODULE__{manage_ref: ref}) do
    Moss.ManageClient.list_indexes(ref)
  end

  @doc "Delete a cloud index."
  @spec delete_index(t(), String.t()) ::
          {:ok, boolean()} | {:error, Moss.Error.t()}
  def delete_index(%__MODULE__{manage_ref: ref}, name) do
    Moss.ManageClient.delete_index(ref, name)
  end

  @doc """
  Get documents from a cloud index.

  Options:
    - `:doc_ids` (list of strings) — if provided, only fetch those docs
  """
  @spec get_docs(t(), String.t(), keyword()) ::
          {:ok, list(Moss.DocumentInfo.t())} | {:error, Moss.Error.t()}
  def get_docs(%__MODULE__{manage_ref: ref}, name, opts \\ []) do
    Moss.ManageClient.get_docs(ref, name, opts)
  end

  # ---------------------------------------------------------------------------
  # Local index ops (delegates to Moss.IndexManager)
  # ---------------------------------------------------------------------------

  @doc """
  Load a cloud index into memory.

  Options:
    - `:auto_refresh` (boolean, default false)
    - `:polling_interval` (integer seconds, default 600, minimum 1; 0 uses
      the default)

  Returns `{:ok, Moss.IndexInfo.t()}` or `{:error, reason}`.
  """
  @spec load_index(t(), String.t(), keyword()) ::
          {:ok, Moss.IndexInfo.t()} | {:error, Moss.Error.t()}
  def load_index(%__MODULE__{manager_pid: pid}, name, opts \\ []) do
    Moss.IndexManager.load_index(pid, name, opts)
  end

  @doc "Unload an index from memory."
  @spec unload_index(t(), String.t()) :: {:ok, :ok} | {:error, Moss.Error.t()}
  def unload_index(%__MODULE__{manager_pid: pid}, name) do
    Moss.IndexManager.unload_index(pid, name)
  end

  @doc "Check if an index is loaded."
  @spec has_index(t(), String.t()) :: boolean()
  def has_index(%__MODULE__{manager_pid: pid}, name) do
    Moss.IndexManager.has_index(pid, name)
  end

  @doc """
  Bulk-load many indexes into memory. Best-effort: names that fail are reported
  in `failed` without rolling back the ones that loaded.

  Options:
    - `:auto_refresh` (boolean, default false)
    - `:polling_interval` (integer seconds, default 600, minimum 1; 0 uses
      the default)

  Returns `{:ok, %Moss.LoadIndexesResult{loaded: [...], failed: %{name => reason}}}`.
  """
  @spec load_indexes(t(), [String.t()], keyword()) :: {:ok, Moss.LoadIndexesResult.t()}
  def load_indexes(%__MODULE__{manager_pid: pid}, names, opts \\ []) do
    Moss.IndexManager.load_indexes(pid, names, opts)
  end

  @doc "Bulk-unload indexes. Idempotent for names that are not loaded."
  @spec unload_indexes(t(), [String.t()]) :: :ok
  def unload_indexes(%__MODULE__{manager_pid: pid}, names) do
    Moss.IndexManager.unload_indexes(pid, names)
  end

  @doc """
  Search several loaded indexes in one call and get the global top-k, each
  result tagged with its source `index_name`. All names must be loaded
  (`load_index/3` or `load_indexes/3`) and share one embedding model.

  `:alpha` works exactly as in `query/4` (default 0.8): `1.0` is embedding-only,
  `0.0` is keyword-only, and values in between fuse both with Reciprocal Rank
  Fusion. Keyword scoring runs each index's own BM25 and merges hits by score
  before fusion. Keyword-only queries never embed the text, so they also work on
  custom-model indexes without `:embedding`.

  Options:
    - `:top_k` (integer, default 10; caps the merged result, not each index)
    - `:alpha` (float, default 0.8)
    - `:filter` (map, applied to every index)
    - `:embedding` (list of floats, required for `model_id: "custom"` unless `alpha: 0.0`)

  Returns `{:ok, Moss.SearchResult.t()}` or `{:error, reason}`.
  """
  @spec query_multi_index(t(), [String.t()], String.t(), keyword()) ::
          {:ok, Moss.SearchResult.t()} | {:error, Moss.Error.t()}
  def query_multi_index(%__MODULE__{manager_pid: pid}, names, query_text, opts \\ []) do
    Moss.IndexManager.query_multi_index(pid, names, query_text, opts)
  end

  @doc """
  Query a locally loaded index.

  For built-in models, the query is embedded automatically. For indexes created
  with `model_id: "custom"`, pass the query embedding via `embedding: [...]`.

  Options:
    - `:top_k` (integer, default 5)
    - `:alpha` (float, default 0.8)
    - `:filter` (map)
    - `:embedding` (list of floats, required for `model_id: "custom"`)

  Returns `{:ok, Moss.SearchResult.t()}` or `{:error, reason}`.
  """
  @spec query(t(), String.t(), String.t(), keyword()) ::
          {:ok, Moss.SearchResult.t()} | {:error, Moss.Error.t()}
  def query(%__MODULE__{manager_pid: pid}, name, query_text, opts \\ []) do
    Moss.IndexManager.query(pid, name, query_text, opts)
  end

  @doc "Install the cloud's snapshot of a loaded index when it is newer. A snapshot no newer than the loaded one, with the same model, downloads nothing and returns `was_updated: false`."
  @spec refresh_index(t(), String.t()) ::
          {:ok, Moss.RefreshResult.t()} | {:error, Moss.Error.t()}
  def refresh_index(%__MODULE__{manager_pid: pid}, name) do
    Moss.IndexManager.refresh_index(pid, name)
  end

  @doc "Get metadata for a loaded index."
  @spec get_index_info(t(), String.t()) ::
          {:ok, Moss.IndexInfo.t()} | {:error, Moss.Error.t()}
  def get_index_info(%__MODULE__{manager_pid: pid}, name) do
    Moss.IndexManager.get_index_info(pid, name)
  end

  # ---------------------------------------------------------------------------
  # Session
  # ---------------------------------------------------------------------------

  @doc """
  Create or resume a local session index.

  If a cloud index with `index_name` already exists, it is silently loaded
  into the session, and the session takes its model, even when the index has no
  documents. If not, the session starts empty. An explicit `:model_id` that the
  existing index does not use returns `{:error, %Moss.Error{code: :invalid_argument}}`.

  With `auto_load_on_init: false` the session skips that load and starts empty
  with `:model_id`, so `Moss.Session.load_from_disk/3` can restore it with no index
  download. `Moss.Session.push_index/1` before any load replaces the cloud index
  with the session's documents.

  Options:
    - `:model_id` (String.t(), default "moss-minilm")
    - `:auto_load_on_init` (boolean, default true): load an existing cloud index
      into the session before returning
    - `:server_name` — GenServer name for the Session process

  Returns `{:ok, pid}` on success.
  """
  @spec session(t(), String.t(), keyword()) ::
          {:ok, GenServer.server()} | {:error, Moss.Error.t()}
  def session(%__MODULE__{} = client, index_name, opts \\ []) do
    requested_model_id = Keyword.get(opts, :model_id)
    model_id = requested_model_id || @default_model_id
    auto_load_on_init = Keyword.get(opts, :auto_load_on_init, true)
    {device_id, moss_device_id} = Moss.IndexManager.device_identity(client.manager_pid)

    # Unlinked start, then link on success: session creation authenticates
    # eagerly, and a linked start would turn an auth failure into an exit
    # signal that kills the caller instead of returning {:error, reason}.
    with {:ok, pid} <-
           Moss.Session.start(
             Keyword.merge(
               Keyword.drop(opts, [:device_id, :moss_device_id, :cache_path, :auto_load_on_init]),
               name: index_name,
               model_id: model_id,
               project_id: client.project_id,
               project_key: client.project_key,
               client_id: client.client_id,
               device_id: device_id,
               moss_device_id: moss_device_id,
               cache_path: client.cache_path
             )
           ) do
      Process.link(pid)
      if auto_load_on_init, do: load_existing_index(pid, index_name)
      loaded_model_id = Moss.Session.model_id(pid)

      with :ok <- check_loaded_model(index_name, requested_model_id, loaded_model_id),
           :ok <- maybe_warm_session_model(pid, loaded_model_id) do
        {:ok, pid}
      else
        {:error, reason} ->
          if Process.alive?(pid), do: GenServer.stop(pid)
          {:error, reason}
      end
    end
  end

  @doc """
  Close the client's index manager: send its final usage telemetry, unload its indexes
  and stop its process.

  Waits until the telemetry is delivered or 2 seconds pass. Sessions are separate
  processes, so close each with `Moss.Session.close/1`. Cloud calls such as
  `create_index/4` keep working afterwards; calls that need the manager exit.
  """
  @spec close(t()) :: :ok
  def close(%__MODULE__{manager_pid: pid}), do: Moss.IndexManager.close(pid)

  # ---------------------------------------------------------------------------
  # Private helpers
  # ---------------------------------------------------------------------------

  @doc false
  def normalize_cache_path(path) when is_binary(path) do
    case String.trim(path) do
      "" -> nil
      trimmed -> ensure_device_id_file(trimmed)
    end
  end

  def normalize_cache_path(_), do: nil

  defp ensure_device_id_file(dir) do
    file = Path.join(dir, ".moss-device-id")

    if not File.exists?(file) do
      with :ok <- File.mkdir_p(dir), do: File.write(file, Uniq.UUID.uuid4())
    end

    dir
  end

  # Errors are logged and ignored, since the index may not exist yet.
  defp load_existing_index(pid, index_name) do
    case Moss.Session.load_index(pid, index_name) do
      {:ok, _doc_count} ->
        :ok

      {:error, reason} ->
        require Logger

        Logger.warning(
          "Could not load existing index '#{index_name}' — starting fresh. Reason: #{reason}"
        )
    end
  end

  # A loaded index, even an empty one, sets the session's model.
  # An explicit :model_id must name that model, or session/3 fails.
  defp check_loaded_model(_index_name, nil, _loaded_model_id), do: :ok
  defp check_loaded_model(_index_name, model_id, model_id), do: :ok

  defp check_loaded_model(index_name, requested_model_id, loaded_model_id) do
    {:error,
     Moss.Error.invalid_argument(
       ~s(Existing session index "#{index_name}" uses model_id "#{loaded_model_id}", ) <>
         ~s(but session/3 was called with model_id: "#{requested_model_id}". ) <>
         "Omit :model_id to adopt the stored model or pass the matching model_id."
     )}
  end

  defp maybe_warm_session_model(pid, model_id) do
    if model_id in ["moss-minilm", "moss-mediumlm"] do
      case Moss.Session.load_model(pid) do
        {:ok, :ok} -> :ok
        {:error, reason} -> {:error, reason}
      end
    else
      :ok
    end
  end
end
