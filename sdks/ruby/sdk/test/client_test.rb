# frozen_string_literal: true

require_relative "test_helper"

class ClientTest < Minitest::Test
  def build_client(manage: nil, index: nil, **opts)
    Moss::Client.new(
      project_id: "pid",
      project_key: "pkey",
      manage_factory: manage ? ->(_id, _key) { manage } : nil,
      index_factory: index ? ->(_id, _key) { index } : nil,
      poll_interval_seconds: 0,
      **opts
    )
  end

  def sample_docs
    [
      Moss::DocumentInfo.new(id: "1", text: "Refunds take 5-7 days.", metadata: { "topic" => "refunds" }),
      Moss::DocumentInfo.new(id: "2", text: "Track orders in the dashboard.", metadata: { "topic" => "shipping" })
    ]
  end

  # ---- credential / argument validation ---------------------------------

  def test_missing_credentials_raise_configuration_error
    client = Moss::Client.new(project_id: nil, project_key: nil)
    assert_raises(Moss::ConfigurationError) { client.list_indexes }
  end

  def test_empty_index_name_raises_argument_error
    client = build_client(manage: TestSupport::FakeManageClient.new)
    assert_raises(Moss::ArgumentError) { client.get_index("  ") }
  end

  def test_empty_documents_raise_argument_error
    client = build_client(manage: TestSupport::FakeManageClient.new)
    assert_raises(Moss::ArgumentError) { client.create_index("docs", []) }
  end

  # ---- create_index: model + embedding resolution -----------------------

  def test_create_index_defaults_to_minilm_and_polls_to_completion
    manage = TestSupport::FakeManageClient.new
    client = build_client(manage: manage)

    result = client.create_index("docs", sample_docs)

    create_call = manage.calls.find { |c| c[0] == :create_index }
    assert_equal "moss-minilm", create_call[3]
    assert_equal "job-1", result.job_id
    assert_equal 2, result.doc_count
    assert(manage.calls.any? { |c| c[0] == :get_job_status })
  end

  def test_create_index_infers_custom_model_from_embeddings
    manage = TestSupport::FakeManageClient.new
    client = build_client(manage: manage)
    docs = [
      Moss::DocumentInfo.new(id: "1", text: "a", embedding: [0.1, 0.2, 0.3]),
      Moss::DocumentInfo.new(id: "2", text: "b", embedding: [0.4, 0.5, 0.6])
    ]

    client.create_index("vec", docs)

    create_call = manage.calls.find { |c| c[0] == :create_index }
    assert_equal "custom", create_call[3]
  end

  def test_create_index_rejects_mixed_embeddings
    client = build_client(manage: TestSupport::FakeManageClient.new)
    docs = [
      Moss::DocumentInfo.new(id: "1", text: "a", embedding: [0.1]),
      Moss::DocumentInfo.new(id: "2", text: "b")
    ]
    assert_raises(Moss::ArgumentError) { client.create_index("vec", docs) }
  end

  def test_create_index_rejects_mismatched_embedding_dimensions
    client = build_client(manage: TestSupport::FakeManageClient.new)
    docs = [
      Moss::DocumentInfo.new(id: "1", text: "a", embedding: [0.1, 0.2]),
      Moss::DocumentInfo.new(id: "2", text: "b", embedding: [0.3])
    ]
    assert_raises(Moss::ArgumentError) { client.create_index("vec", docs) }
  end

  def test_create_index_rejects_custom_model_without_embeddings
    client = build_client(manage: TestSupport::FakeManageClient.new)
    assert_raises(Moss::ArgumentError) do
      client.create_index("vec", sample_docs, model_id: "custom")
    end
  end

  # ---- job polling ------------------------------------------------------

  def test_failed_job_raises_job_error
    manage = TestSupport::FakeManageClient.new(job_status_sequence: ["failed"])
    client = build_client(manage: manage)
    assert_raises(Moss::JobError) { client.create_index("docs", sample_docs) }
  end

  def test_on_progress_callback_receives_updates
    manage = TestSupport::FakeManageClient.new(job_status_sequence: %w[building completed])
    client = build_client(manage: manage)
    seen = []

    client.create_index("docs", sample_docs, on_progress: ->(p) { seen << p.status })

    assert_includes seen, "building"
    assert_includes seen, "completed"
  end

  # ---- metadata normalisation -------------------------------------------

  def test_metadata_is_stringified_for_native_layer
    manage = TestSupport::FakeManageClient.new
    client = build_client(manage: manage)
    docs = [Moss::DocumentInfo.new(id: "1", text: "a", metadata: { topic: :refunds, count: 3 })]

    client.create_index("docs", docs)

    core_docs = manage.calls.find { |c| c[0] == :create_index }[2]
    assert_equal({ "topic" => "refunds", "count" => "3" }, core_docs.first.metadata)
  end

  # ---- reads ------------------------------------------------------------

  def test_list_indexes_maps_to_high_level_models
    client = build_client(manage: TestSupport::FakeManageClient.new)
    indexes = client.list_indexes
    assert_kind_of Moss::IndexInfo, indexes.first
    assert_equal "docs", indexes.first.name
    assert_equal "moss-minilm", indexes.first.model.id
  end

  def test_get_documents_maps_metadata
    client = build_client(manage: TestSupport::FakeManageClient.new)
    docs = client.get_documents("docs")
    assert_kind_of Moss::DocumentInfo, docs.first
    assert_equal({ "k" => "v" }, docs.first.metadata)
  end

  # ---- query routing ----------------------------------------------------

  def test_query_uses_local_manager_when_index_loaded
    index = TestSupport::FakeIndexManager.new(loaded: ["docs"])
    client = build_client(manage: TestSupport::FakeManageClient.new, index: index)

    filter = { "field" => "topic", "condition" => { "$eq" => "refunds" } }
    result = client.query("docs", "hello", top_k: 3, alpha: 0.5, filter: filter)

    assert_kind_of Moss::SearchResult, result
    query_call = index.calls.find { |c| c[0] == :query }
    assert_equal 3, query_call[4]                       # top_k
    assert_in_delta 0.5, query_call[5], 0.0001          # alpha
    assert_equal JSON.generate(filter), query_call[6]   # filter_json passed through verbatim
    assert_equal 0.9, result.docs.first.score
  end

  def test_query_falls_back_to_cloud_when_index_not_loaded
    index = TestSupport::FakeIndexManager.new(loaded: [])
    client = build_client(manage: TestSupport::FakeManageClient.new, index: index)

    # Stub the cloud path so no network call happens.
    captured = nil
    replacement = lambda { |**kwargs|
      captured = kwargs
      Moss::SearchResult.new(docs: [], query: kwargs[:query], index_name: kwargs[:index_name], time_taken_ms: 1)
    }
    TestSupport.with_stubbed_singleton(Moss::CloudQuery, :execute, replacement) do
      client.query("docs", "hello", top_k: 7)
    end

    refute_nil captured
    assert_equal "docs", captured[:index_name]
    assert_equal 7, captured[:options].top_k
    assert(index.calls.none? { |c| c[0] == :query })
  end

  def test_cloud_query_raises_when_manage_url_has_no_derivable_query_endpoint
    # manage_url without "/v1/manage" and no explicit query_url => query URL is
    # undecidable, so the cloud fallback must fail fast rather than POST to the
    # manage endpoint.
    index = TestSupport::FakeIndexManager.new(loaded: [])
    client = build_client(
      manage: TestSupport::FakeManageClient.new, index: index,
      manage_url: "https://custom.example/api"
    )
    assert_raises(Moss::ConfigurationError) { client.query("docs", "hello") }
  end

  def test_cloud_query_uses_explicit_query_url_when_manage_url_is_custom
    index = TestSupport::FakeIndexManager.new(loaded: [])
    client = build_client(
      manage: TestSupport::FakeManageClient.new, index: index,
      manage_url: "https://custom.example/api", query_url: "https://custom.example/search"
    )
    captured = nil
    replacement = lambda { |**kwargs|
      captured = kwargs
      Moss::SearchResult.new(docs: [], query: kwargs[:query], index_name: kwargs[:index_name], time_taken_ms: 1)
    }
    TestSupport.with_stubbed_singleton(Moss::CloudQuery, :execute, replacement) do
      client.query("docs", "hello")
    end
    assert_equal "https://custom.example/search", captured[:query_url]
  end

  def test_search_is_an_alias_for_query
    index = TestSupport::FakeIndexManager.new(loaded: ["docs"])
    client = build_client(manage: TestSupport::FakeManageClient.new, index: index)
    assert_kind_of Moss::SearchResult, client.search("docs", "hello")
  end

  # ---- load / unload ----------------------------------------------------

  def test_load_index_returns_name_and_tracks_loaded_state
    index = TestSupport::FakeIndexManager.new
    client = build_client(manage: TestSupport::FakeManageClient.new, index: index)

    assert_equal "docs", client.load_index("docs")
    assert index.has_index?("docs")
  end

  def test_load_index_rejects_cache_path
    index = TestSupport::FakeIndexManager.new
    client = build_client(manage: TestSupport::FakeManageClient.new, index: index)
    assert_raises(Moss::ArgumentError) { client.load_index("docs", cache_path: "/tmp/cache") }
  end

  # ---- close ------------------------------------------------------------

  def test_close_releases_manage_client
    manage = TestSupport::FakeManageClient.new
    client = build_client(manage: manage)
    client.list_indexes # force lazy init
    client.close
    assert manage.closed?
  end
end
