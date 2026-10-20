defmodule Moss.ManageClient do
  @moduledoc false

  alias MossCore.Nif

  @doc """
  Create a new ManageClient reference.

  Options:
    - `:client_id` — optional client identifier
  """
  @spec new(String.t(), String.t(), keyword()) ::
          {:ok, reference()} | {:error, Moss.Error.t()}
  def new(project_id, project_key, opts \\ []) do
    client_id = Keyword.get(opts, :client_id, nil)
    Nif.manage_new(project_id, project_key, nil, client_id)
  end

  @doc "Create a cloud index with initial documents."
  @spec create_index(reference(), String.t(), list(Moss.DocumentInfo.t()), String.t()) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def create_index(ref, name, docs, model_id) do
    Nif.manage_create_index(ref, name, docs, model_id)
  end

  @doc """
  Add documents to an existing cloud index.

  Options:
    - `:upsert` (boolean, default nil — use server default)
  """
  @spec add_docs(reference(), String.t(), list(Moss.DocumentInfo.t()), keyword()) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def add_docs(ref, name, docs, opts \\ []) do
    upsert = Keyword.get(opts, :upsert, nil)
    Nif.manage_add_docs(ref, name, docs, upsert)
  end

  @doc "Delete documents by IDs from a cloud index."
  @spec delete_docs(reference(), String.t(), list(String.t())) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def delete_docs(ref, name, doc_ids) do
    Nif.manage_delete_docs(ref, name, doc_ids)
  end

  @doc """
  Create an index from raw files via the server-side parse pipeline.

  Each file in `files` is a map with:
    - `:name` (required) — filename sent to server
    - `:content_type` (required) — MIME type (e.g. `"application/pdf"`)
    - `:path` (required) — filesystem path to the file

  `model_id` must be a built-in model ("moss-minilm" or "moss-mediumlm").
  "custom" is not supported because the parse pipeline generates embeddings server-side.

  At most 20 files per call.

  Returns `{:ok, Moss.MutationResult.t()}` or `{:error, reason}`.
  """
  @spec create_index_from_files(
          reference(),
          String.t(),
          list(map()),
          String.t(),
          map() | nil
        ) ::
          {:ok, Moss.MutationResult.t()} | {:error, Moss.Error.t()}
  def create_index_from_files(ref, name, files, model_id, parse_options \\ nil) do
    nif_files =
      Enum.map(files, fn f ->
        %{
          "name" => Map.fetch!(f, :name),
          "content_type" => Map.fetch!(f, :content_type),
          "path" => Map.fetch!(f, :path)
        }
      end)

    Nif.manage_create_index_from_files(ref, name, nif_files, model_id, parse_options)
  end

  @doc "Poll the status of an async job."
  @spec get_job_status(reference(), String.t()) ::
          {:ok, Moss.JobStatusResponse.t()} | {:error, Moss.Error.t()}
  def get_job_status(ref, job_id) do
    Nif.manage_get_job_status(ref, job_id)
  end

  @doc "Get metadata for a cloud index."
  @spec get_index(reference(), String.t()) ::
          {:ok, Moss.IndexInfo.t()} | {:error, Moss.Error.t()}
  def get_index(ref, name) do
    Nif.manage_get_index(ref, name)
  end

  @doc "List all cloud indexes for this project."
  @spec list_indexes(reference()) ::
          {:ok, list(Moss.IndexInfo.t())} | {:error, Moss.Error.t()}
  def list_indexes(ref) do
    Nif.manage_list_indexes(ref)
  end

  @doc "Delete a cloud index."
  @spec delete_index(reference(), String.t()) ::
          {:ok, boolean()} | {:error, Moss.Error.t()}
  def delete_index(ref, name) do
    Nif.manage_delete_index(ref, name)
  end

  @doc """
  Get documents from a cloud index.

  Options:
    - `:doc_ids` (list of strings) — if provided, only fetch those docs
  """
  @spec get_docs(reference(), String.t(), keyword()) ::
          {:ok, list(Moss.DocumentInfo.t())} | {:error, Moss.Error.t()}
  def get_docs(ref, name, opts \\ []) do
    doc_ids = Keyword.get(opts, :doc_ids, nil)
    Nif.manage_get_docs(ref, name, doc_ids)
  end

  @doc "Validate project credentials."
  @spec validate_credentials(reference()) ::
          {:ok, Moss.CredentialsInfo.t()} | {:error, Moss.Error.t()}
  def validate_credentials(ref) do
    Nif.manage_validate_credentials(ref)
  end
end
