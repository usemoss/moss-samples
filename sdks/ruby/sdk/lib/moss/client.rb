# frozen_string_literal: true

require "json"
require "moss/core"
require_relative "errors"
require_relative "models"
require_relative "cloud_query"
require_relative "session"

module Moss
  # The high-level Moss client. Wraps the native binding layer (Moss::Core) for
  # mutations, local index loading and sub-10ms local queries, and falls back to
  # the cloud query API when an index is not loaded locally (or libmoss is
  # unavailable).
  #
  # Credentials are read from the constructor or, when omitted, from the
  # MOSS_PROJECT_ID / MOSS_PROJECT_KEY environment variables.
  #
  #   client = Moss::Client.new                       # creds from ENV
  #   client.create_index("docs", documents)
  #   client.load_index("docs")
  #   client.query("docs", "how do refunds work?", top_k: 3)
  class Client
    DEFAULT_MANAGE_URL = "https://service.usemoss.dev/v1/manage"
    DEFAULT_TOP_K = Moss::Core::DEFAULT_TOP_K
    DEFAULT_ALPHA = Moss::Core::DEFAULT_ALPHA

    DEFAULT_POLL_INTERVAL_SECONDS = 2.0
    DEFAULT_MUTATION_TIMEOUT_SECONDS = 30 * 60
    MAX_CONSECUTIVE_POLL_ERRORS = 3

    # Call-shaping options for #query. Mirrors the fields other SDKs accept.
    # The :filter member intentionally shadows Struct#filter; this object is a
    # plain value holder and is never used as an Enumerable.
    QueryOptions = Struct.new(:embedding, :top_k, :alpha, :filter, keyword_init: true) # rubocop:disable Lint/StructNewOverride

    def initialize(project_id: nil, project_key: nil, manage_url: nil, query_url: nil,
                   http_open_timeout: 10, http_read_timeout: 60,
                   poll_interval_seconds: DEFAULT_POLL_INTERVAL_SECONDS,
                   manage_factory: nil, index_factory: nil)
      @project_id = string_or_nil(project_id) || string_or_nil(ENV.fetch("MOSS_PROJECT_ID", nil))
      @project_key = string_or_nil(project_key) || string_or_nil(ENV.fetch("MOSS_PROJECT_KEY", nil))
      @manage_url = string_or_nil(manage_url) || string_or_nil(ENV.fetch("MOSS_CLOUD_API_MANAGE_URL",
                                                                         nil)) || DEFAULT_MANAGE_URL
      @query_url = resolve_query_url(query_url)
      @http_open_timeout = http_open_timeout
      @http_read_timeout = http_read_timeout
      @poll_interval_seconds = poll_interval_seconds

      # Runtime factories are injectable so the SDK can be unit-tested without
      # libmoss present (mirrors the Go SDK's manageFactory/indexFactory).
      @manage_factory = manage_factory || ->(id, key) { Moss::Core::ManageClient.new(id, key) }
      @index_factory = index_factory || ->(id, key) { Moss::Core::IndexManager.new(id, key) }

      @manage_mutex = Mutex.new
      @index_mutex = Mutex.new
      @manage_client = nil
      @index_manager = nil
      @index_manager_unavailable = false
    end

    # ---- manage: mutations ------------------------------------------------

    def create_index(index_name, documents, model_id: nil, on_progress: nil)
      validate_manage_request(index_name)
      raise ArgumentError, "moss: documents must not be empty" if documents.nil? || documents.empty?

      resolved_model = resolve_model_id(documents, model_id)
      validate_embedding_dimensions(documents, resolved_model)

      manage = ensure_manage_client
      result = manage.create_index(index_name, to_core_documents(documents), resolved_model)
      poll_job_until_complete(result, on_progress)
    end

    def add_documents(index_name, documents, upsert: nil, on_progress: nil)
      validate_manage_request(index_name)
      raise ArgumentError, "moss: documents must not be empty" if documents.nil? || documents.empty?

      options = upsert.nil? ? nil : Moss::Core::MutationOptions.new(upsert: upsert)
      manage = ensure_manage_client
      result = manage.add_docs(index_name, to_core_documents(documents), options)
      poll_job_until_complete(result, on_progress)
    end
    alias add_docs add_documents

    def delete_documents(index_name, doc_ids, on_progress: nil)
      validate_manage_request(index_name)
      raise ArgumentError, "moss: document IDs must not be empty" if doc_ids.nil? || doc_ids.empty?

      manage = ensure_manage_client
      result = manage.delete_docs(index_name, Array(doc_ids).map(&:to_s))
      poll_job_until_complete(result, on_progress)
    end
    alias delete_docs delete_documents

    def get_job_status(job_id)
      validate_credentials
      raise ArgumentError, "moss: job ID must not be empty" if string_or_nil(job_id).nil?

      to_job_status(ensure_manage_client.get_job_status(job_id))
    end

    # ---- manage: reads ----------------------------------------------------

    def get_index(index_name)
      validate_manage_request(index_name)
      to_index_info(ensure_manage_client.get_index(index_name))
    end

    def list_indexes
      validate_credentials
      ensure_manage_client.list_indexes.map { |info| to_index_info(info) }
    end

    def delete_index(index_name)
      validate_manage_request(index_name)
      ensure_manage_client.delete_index(index_name)
    end

    def get_documents(index_name, doc_ids: nil)
      validate_manage_request(index_name)
      ids = doc_ids.nil? ? [] : Array(doc_ids).map(&:to_s)
      ensure_manage_client.get_docs(index_name, ids).map { |doc| to_document(doc) }
    end
    alias get_docs get_documents

    # ---- local index runtime ---------------------------------------------

    def load_index(index_name, auto_refresh: false, polling_interval_in_seconds: 0, cache_path: nil)
      validate_manage_request(index_name)
      unless cache_path.nil? || cache_path.to_s.strip.empty?
        raise ArgumentError, "moss: cache_path is not supported by the current libmoss bindings"
      end

      options = Moss::Core::LoadIndexOptions.new(
        auto_refresh: auto_refresh,
        polling_interval_secs: polling_interval_in_seconds
      )
      manager = require_index_manager
      info = manager.load_index(index_name, options)
      manager.load_query_model(index_name) if info.model && info.model.id != Model::CUSTOM
      info.name && !info.name.empty? ? info.name : index_name
    end

    def unload_index(index_name)
      raise ArgumentError, "moss: index name must not be empty" if string_or_nil(index_name).nil?

      require_index_manager.unload_index(index_name)
      nil
    end

    def refresh_index(index_name)
      validate_manage_request(index_name)
      to_refresh_result(require_index_manager.refresh_index(index_name))
    end

    def get_index_info(index_name)
      validate_manage_request(index_name)
      to_index_info(require_index_manager.get_index_info(index_name))
    end

    # ---- query (local, else cloud fallback) -------------------------------

    def query(index_name, query_text = "", embedding: nil, top_k: nil, alpha: nil, filter: nil)
      validate_query_request(index_name)
      options = QueryOptions.new(embedding: embedding, top_k: top_k, alpha: alpha, filter: filter)

      manager = ensure_index_manager
      if manager&.has_index?(index_name)
        query_local(manager, index_name, query_text.to_s, options)
      else
        query_cloud(index_name, query_text.to_s, options)
      end
    end
    alias search query

    # ---- sessions ---------------------------------------------------------

    def session(index_name, model_id: nil)
      validate_manage_request(index_name)
      options = model_id.nil? ? nil : Moss::Core::SessionOptions.new(model_id: model_id)
      core_session = ensure_manage_client.session(index_name, options)
      Session.new(core_session)
    end

    # Releases the lazily created native runtime handles.
    def close
      manage = nil
      manager = nil
      @manage_mutex.synchronize do
        manage = @manage_client
        @manage_client = nil
      end
      @index_mutex.synchronize do
        manager = @index_manager
        @index_manager = nil
      end
      manage&.close
      manager&.close
      nil
    end

    private

    # ---- query helpers ----------------------------------------------------

    def query_local(manager, index_name, query_text, options)
      top_k = positive_or_default(options.top_k, DEFAULT_TOP_K)
      alpha = options.alpha.nil? ? DEFAULT_ALPHA : options.alpha.to_f
      filter_json =
        (JSON.generate(options.filter) if options.filter && !options.filter.empty?)

      result = manager.query(
        index_name, query_text,
        embedding: options.embedding, top_k: top_k, alpha: alpha, filter_json: filter_json
      )
      to_search_result(result)
    end

    def query_cloud(index_name, query_text, options)
      CloudQuery.execute(
        query_url: @query_url,
        project_id: @project_id,
        project_key: @project_key,
        index_name: index_name,
        query: query_text,
        options: options,
        http_open_timeout: @http_open_timeout,
        http_read_timeout: @http_read_timeout
      )
    end

    # ---- job polling ------------------------------------------------------

    def poll_job_until_complete(mutation_result, on_progress)
      completed = to_mutation_result(mutation_result)
      deadline = monotonic_now + DEFAULT_MUTATION_TIMEOUT_SECONDS
      consecutive_errors = 0

      loop do
        begin
          status = get_job_status(mutation_result.job_id)
          consecutive_errors = 0

          on_progress&.call(
            JobProgress.new(
              job_id: status.job_id,
              status: status.status,
              progress: status.progress,
              current_phase: status.current_phase
            )
          )

          case status.status
          when JobStatus::COMPLETED
            return completed
          when JobStatus::FAILED
            message = status.error && !status.error.empty? ? "moss: job failed: #{status.error}" : "moss: job failed"
            raise JobError, message
          end
        rescue JobError
          raise
        rescue StandardError => e
          consecutive_errors += 1
          if consecutive_errors >= MAX_CONSECUTIVE_POLL_ERRORS
            raise JobError, "moss: job status polling failed after " \
                            "#{MAX_CONSECUTIVE_POLL_ERRORS} consecutive errors: #{e.message}"
          end
        end

        raise JobError, "moss: timed out waiting for job #{mutation_result.job_id}" if monotonic_now > deadline

        sleep(@poll_interval_seconds)
      end
    end

    def monotonic_now
      Process.clock_gettime(Process::CLOCK_MONOTONIC)
    end

    # ---- model / embedding resolution ------------------------------------

    def resolve_model_id(documents, model_id)
      resolved = string_or_nil(model_id)
      return resolved if resolved
      return Model::CUSTOM if documents.any? { |doc| non_empty_embedding?(doc) }

      Model::MOSS_MINILM
    end

    def validate_embedding_dimensions(documents, model_id)
      with_embeddings = documents.select { |doc| non_empty_embedding?(doc) }
      without_embeddings = documents.length - with_embeddings.length

      if !with_embeddings.empty? && without_embeddings.positive?
        raise ArgumentError,
              "moss: all documents must either all have embeddings or none should have embeddings"
      end

      if with_embeddings.empty?
        if model_id == Model::CUSTOM
          raise ArgumentError, "moss: cannot use model \"#{Model::CUSTOM}\" without pre-computed embeddings"
        end

        return
      end

      dimension = embedding_of(with_embeddings.first).length
      with_embeddings.each do |doc|
        actual = embedding_of(doc).length
        next if actual == dimension

        raise ArgumentError,
              "moss: document \"#{doc.id}\" has mismatched embedding dimension (expected #{dimension}, got #{actual})"
      end
    end

    def non_empty_embedding?(doc)
      embedding = embedding_of(doc)
      embedding && !embedding.empty?
    end

    def embedding_of(doc)
      doc.respond_to?(:embedding) ? doc.embedding : doc[:embedding]
    end

    # ---- runtime lifecycle ------------------------------------------------

    def ensure_manage_client
      @manage_mutex.synchronize do
        return @manage_client if @manage_client

        begin
          @manage_client = @manage_factory.call(@project_id, @project_key)
        rescue Moss::Core::BindingsUnavailableError => e
          raise ConfigurationError, e.message
        end
      end
    end

    # Returns the IndexManager, or nil if libmoss is unavailable (query falls
    # back to the cloud in that case).
    def ensure_index_manager
      @index_mutex.synchronize do
        return @index_manager if @index_manager
        return nil if @index_manager_unavailable

        begin
          @index_manager = @index_factory.call(@project_id, @project_key)
        rescue Moss::Core::BindingsUnavailableError
          @index_manager_unavailable = true
          nil
        end
      end
    end

    # Like ensure_index_manager but raises when libmoss is unavailable — used by
    # operations that have no cloud fallback (load/unload/refresh/local info).
    def require_index_manager
      manager = ensure_index_manager
      raise ConfigurationError, Moss::Core::BindingsUnavailableError::DEFAULT_MESSAGE unless manager

      manager
    end

    # ---- validation -------------------------------------------------------

    def validate_manage_request(index_name)
      validate_credentials
      raise ArgumentError, "moss: index name must not be empty" if string_or_nil(index_name).nil?
    end
    alias validate_query_request validate_manage_request

    def validate_credentials
      raise ConfigurationError, "moss: missing project ID" if @project_id.nil?
      raise ConfigurationError, "moss: missing project key" if @project_key.nil?
    end

    def resolve_query_url(explicit)
      value = string_or_nil(explicit) || string_or_nil(ENV.fetch("MOSS_CLOUD_QUERY_URL", nil))
      return value if value
      return nil if @manage_url.nil? || @manage_url.empty?

      # Derive the query endpoint from the manage endpoint only when the
      # substitution actually changes the URL. If manage_url was overridden to a
      # value without "/v1/manage", return nil so the cloud fallback fails fast
      # with a clear ConfigurationError instead of silently POSTing to the
      # manage endpoint; callers can set query_url / MOSS_CLOUD_QUERY_URL.
      derived = @manage_url.sub("/v1/manage", "/query")
      derived == @manage_url ? nil : derived
    end

    # ---- conversions (Core -> Moss) ---------------------------------------

    def to_core_documents(documents)
      documents.map do |doc|
        Moss::Core::DocumentInfo.new(
          id: doc.id.to_s,
          text: (doc.text || "").to_s,
          metadata: normalize_metadata(doc.metadata),
          embedding: embedding_of(doc)
        )
      end
    end

    def normalize_metadata(metadata)
      return nil if metadata.nil? || metadata.empty?

      metadata.each_with_object({}) do |(key, value), acc|
        acc[key.to_s] = value.to_s
      end
    end

    def to_index_info(core)
      IndexInfo.new(
        id: core.id,
        name: core.name,
        version: core.version,
        status: core.status,
        doc_count: core.doc_count,
        created_at: core.created_at,
        updated_at: core.updated_at,
        model: ModelRef.new(id: core.model&.id, version: core.model&.version)
      )
    end

    def to_document(core)
      DocumentInfo.new(
        id: core.id,
        text: core.text,
        metadata: core.metadata,
        embedding: core.embedding
      )
    end

    def to_mutation_result(core)
      MutationResult.new(job_id: core.job_id, index_name: core.index_name, doc_count: core.doc_count)
    end

    def to_search_result(core)
      docs = core.docs.map do |doc|
        QueryResultDocument.new(id: doc.id, text: doc.text, metadata: doc.metadata, score: doc.score)
      end
      SearchResult.new(
        docs: docs,
        query: core.query,
        index_name: core.index_name,
        time_taken_ms: core.time_taken_ms
      )
    end

    def to_job_status(core)
      JobStatusResponse.new(
        job_id: core.job_id,
        status: core.status,
        progress: core.progress,
        current_phase: core.current_phase,
        error: core.error,
        created_at: core.created_at,
        updated_at: core.updated_at,
        completed_at: core.completed_at
      )
    end

    def to_refresh_result(core)
      RefreshResult.new(
        index_name: core.index_name,
        previous_updated_at: core.previous_updated_at,
        new_updated_at: core.new_updated_at,
        was_updated: core.was_updated
      )
    end

    # ---- misc -------------------------------------------------------------

    def positive_or_default(value, default)
      value&.to_i&.positive? ? value.to_i : default
    end

    def string_or_nil(value)
      return nil if value.nil?

      stripped = value.to_s.strip
      stripped.empty? ? nil : stripped
    end
  end
end
