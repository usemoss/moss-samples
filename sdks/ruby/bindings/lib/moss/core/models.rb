# frozen_string_literal: true

module Moss
  module Core
    # Default local-query parameters shared by IndexManager and Session.
    DEFAULT_TOP_K = 5
    DEFAULT_ALPHA = 0.8

    # Plain-Ruby value objects returned by the binding layer. These intentionally
    # mirror the C structs in libmoss.h field-for-field; the high-level `moss`
    # gem re-maps them onto its own richer models. Keyword-initialized Structs
    # keep them immutable-ish and cheap to construct from marshalled native data.

    DocumentInfo = Struct.new(:id, :text, :metadata, :embedding, keyword_init: true) do
      def initialize(id:, text:, metadata: nil, embedding: nil)
        super
      end
    end

    ModelRef = Struct.new(:id, :version, keyword_init: true)

    IndexInfo = Struct.new(
      :id, :name, :version, :status, :doc_count,
      :created_at, :updated_at, :model,
      keyword_init: true
    )

    MutationResult = Struct.new(:job_id, :index_name, :doc_count, keyword_init: true)

    JobStatusResponse = Struct.new(
      :job_id, :status, :progress, :current_phase, :error,
      :created_at, :updated_at, :completed_at,
      keyword_init: true
    )

    QueryResultDocument = Struct.new(:id, :text, :metadata, :score, keyword_init: true)

    SearchResult = Struct.new(
      :docs, :query, :index_name, :time_taken_ms,
      keyword_init: true
    )

    RefreshResult = Struct.new(
      :index_name, :previous_updated_at, :new_updated_at, :was_updated,
      keyword_init: true
    )

    PushIndexResult = Struct.new(
      :job_id, :index_name, :doc_count, :status,
      keyword_init: true
    )

    # Counts returned by Session#add_docs (added vs. upserted-over documents).
    SessionAddResult = Struct.new(:added, :updated, keyword_init: true)

    # Options accepted by the binding layer (distinct from the high-level SDK
    # option objects). Nil fields mean "use the native default".
    MutationOptions = Struct.new(:upsert, keyword_init: true)
    LoadIndexOptions = Struct.new(:auto_refresh, :polling_interval_secs, keyword_init: true)
    SessionOptions = Struct.new(:model_id, keyword_init: true)
  end
end
