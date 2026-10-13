# frozen_string_literal: true

module Moss
  # Embedding models that can back an index.
  module Model
    MOSS_MINILM   = "moss-minilm"
    MOSS_MEDIUMLM = "moss-mediumlm"
    CUSTOM        = "custom"
  end

  # Lifecycle states reported for an index.
  module IndexStatus
    NOT_STARTED = "NotStarted"
    BUILDING    = "Building"
    READY       = "Ready"
    FAILED      = "Failed"
  end

  # Lifecycle states reported for an async mutation job.
  module JobStatus
    PENDING_UPLOAD = "pending_upload"
    UPLOADING      = "uploading"
    BUILDING       = "building"
    COMPLETED      = "completed"
    FAILED         = "failed"
  end

  # A document to index or one already stored. `metadata` is a String=>String
  # map; `embedding` is an optional array of floats for custom-embedding indexes.
  DocumentInfo = Struct.new(:id, :text, :metadata, :embedding, keyword_init: true) do
    def initialize(id:, text: nil, metadata: nil, embedding: nil)
      super
    end
  end

  # A single scored result from a query.
  QueryResultDocument = Struct.new(:id, :text, :metadata, :score, keyword_init: true)

  # The response returned by Client#query / Client#search.
  SearchResult = Struct.new(:docs, :query, :index_name, :time_taken_ms, keyword_init: true)

  # Points at the embedding model backing an index.
  ModelRef = Struct.new(:id, :version, keyword_init: true)

  # Persisted metadata for an index.
  IndexInfo = Struct.new(
    :id, :name, :version, :status, :doc_count,
    :created_at, :updated_at, :model,
    keyword_init: true
  )

  # Returned when a mutation job completes.
  MutationResult = Struct.new(:job_id, :index_name, :doc_count, keyword_init: true)

  # Emitted to an on_progress callback while a mutation job runs.
  JobProgress = Struct.new(:job_id, :status, :progress, :current_phase, keyword_init: true)

  # Persisted status view for a mutation job.
  JobStatusResponse = Struct.new(
    :job_id, :status, :progress, :current_phase, :error,
    :created_at, :updated_at, :completed_at,
    keyword_init: true
  )

  # Outcome of a local RefreshIndex.
  RefreshResult = Struct.new(
    :index_name, :previous_updated_at, :new_updated_at, :was_updated,
    keyword_init: true
  )
end
