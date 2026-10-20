# The NIF fills in these structs from its NifStruct definitions,
# so only fields the Rust side types as Option<_> are nilable here.

defmodule Moss.ModelRef do
  @moduledoc "Model reference (id + version)."
  defstruct [:id, :version]

  @type t :: %__MODULE__{id: String.t(), version: String.t() | nil}
end

defmodule Moss.DocumentInfo do
  @moduledoc "A document with id, text, optional metadata, and optional embedding."
  defstruct [:id, :text, metadata: nil, embedding: nil]

  @type t :: %__MODULE__{
          id: String.t(),
          text: String.t(),
          metadata: %{String.t() => String.t()} | nil,
          embedding: [float()] | nil
        }
end

defmodule Moss.QueryResultDoc do
  @moduledoc "A query result document with a relevance score. `index_name` is set on multi-index results."
  defstruct [:id, :text, :score, metadata: nil, index_name: nil]

  @type t :: %__MODULE__{
          id: String.t(),
          text: String.t(),
          score: float(),
          metadata: %{String.t() => String.t()} | nil,
          index_name: String.t() | nil
        }
end

defmodule Moss.LoadIndexesResult do
  @moduledoc """
  Outcome of a best-effort bulk `load_indexes` call.

  `failed` maps each name that did not load to a fixed message, and
  `failed_codes` maps it to the same code atom `Moss.Error` carries.
  """
  defstruct loaded: [], failed: %{}, failed_codes: %{}

  @type t :: %__MODULE__{
          loaded: [String.t()],
          failed: %{String.t() => String.t()},
          failed_codes: %{String.t() => Moss.Error.code()}
        }
end

defmodule Moss.SearchResult do
  @moduledoc "The result of a search/query operation."
  defstruct [:docs, :query, :index_name, :time_taken_ms]

  @type t :: %__MODULE__{
          docs: [Moss.QueryResultDoc.t()],
          query: String.t(),
          index_name: String.t() | nil,
          time_taken_ms: non_neg_integer() | nil
        }
end

defmodule Moss.IndexInfo do
  @moduledoc "Metadata about a cloud or local index."
  defstruct [:id, :name, :version, :status, :doc_count, :created_at, :updated_at, :model]

  @type t :: %__MODULE__{
          id: String.t(),
          name: String.t(),
          version: String.t() | nil,
          status: String.t(),
          doc_count: non_neg_integer(),
          created_at: String.t() | nil,
          updated_at: String.t() | nil,
          model: Moss.ModelRef.t()
        }
end

defmodule Moss.PushIndexResult do
  @moduledoc "Result of a push_index operation."
  defstruct [:job_id, :index_name, :doc_count, :status]

  @type t :: %__MODULE__{
          job_id: String.t(),
          index_name: String.t(),
          doc_count: non_neg_integer(),
          status: String.t()
        }
end

defmodule Moss.RefreshResult do
  @moduledoc "Result of a refresh_index operation."
  defstruct [:index_name, :previous_updated_at, :new_updated_at, :was_updated]

  @type t :: %__MODULE__{
          index_name: String.t(),
          previous_updated_at: String.t(),
          new_updated_at: String.t(),
          was_updated: boolean()
        }
end

defmodule Moss.SerializedIndex do
  @moduledoc false
  defstruct [:name, :version, :model, :dimension, :embeddings, :doc_ids]

  @type t :: %__MODULE__{
          name: String.t() | nil,
          version: String.t() | nil,
          model: String.t() | nil,
          dimension: non_neg_integer() | nil,
          embeddings: [[float()]] | nil,
          doc_ids: [String.t()] | nil
        }
end

defmodule Moss.MutationResult do
  @moduledoc "Result of a cloud mutation (create, add_docs, delete_docs)."
  defstruct [:job_id, :index_name, :doc_count]

  @type t :: %__MODULE__{
          job_id: String.t(),
          index_name: String.t(),
          doc_count: non_neg_integer()
        }
end

defmodule Moss.JobStatusResponse do
  @moduledoc "Full job status response from the cloud."
  defstruct [
    :job_id,
    :status,
    :progress,
    :current_phase,
    :error,
    :created_at,
    :updated_at,
    :completed_at
  ]

  @type t :: %__MODULE__{
          job_id: String.t(),
          status: String.t(),
          progress: float(),
          current_phase: String.t() | nil,
          error: String.t() | nil,
          created_at: String.t(),
          updated_at: String.t(),
          completed_at: String.t() | nil
        }
end

defmodule Moss.CredentialsInfo do
  @moduledoc false
  defstruct [:project_name, :project_id]

  @type t :: %__MODULE__{project_name: String.t(), project_id: String.t()}
end
