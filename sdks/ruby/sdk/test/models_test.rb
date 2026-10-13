# frozen_string_literal: true

require_relative "test_helper"

class ModelsTest < Minitest::Test
  def test_document_info_defaults
    doc = Moss::DocumentInfo.new(id: "1")
    assert_equal "1", doc.id
    assert_nil doc.text
    assert_nil doc.metadata
    assert_nil doc.embedding
  end

  def test_document_info_full
    doc = Moss::DocumentInfo.new(id: "1", text: "hi", metadata: { "a" => "b" }, embedding: [0.1])
    assert_equal "hi", doc.text
    assert_equal({ "a" => "b" }, doc.metadata)
    assert_equal [0.1], doc.embedding
  end

  def test_model_and_status_constants
    assert_equal "moss-minilm", Moss::Model::MOSS_MINILM
    assert_equal "custom", Moss::Model::CUSTOM
    assert_equal "Ready", Moss::IndexStatus::READY
    assert_equal "completed", Moss::JobStatus::COMPLETED
  end
end

class CloudQueryTest < Minitest::Test
  def base_args
    {
      query_url: "https://example.test/query",
      project_id: "pid",
      project_key: "pkey",
      index_name: "docs",
      query: "hello",
      http_open_timeout: 1,
      http_read_timeout: 1
    }
  end

  def test_missing_query_url_raises_configuration_error
    assert_raises(Moss::ConfigurationError) do
      Moss::CloudQuery.execute(**base_args, query_url: "", options: nil)
    end
  end

  def test_alpha_option_rejected_for_cloud_query
    options = Moss::Client::QueryOptions.new(alpha: 0.5)
    assert_raises(Moss::UnsupportedQueryError) do
      Moss::CloudQuery.execute(**base_args, options: options)
    end
  end

  def test_filter_option_rejected_for_cloud_query
    options = Moss::Client::QueryOptions.new(filter: { "topic" => "refunds" })
    assert_raises(Moss::UnsupportedQueryError) do
      Moss::CloudQuery.execute(**base_args, options: options)
    end
  end

  def test_parse_response_maps_docs
    body = JSON.generate(
      "docs" => [{ "id" => "1", "text" => "hi", "metadata" => { "k" => "v" }, "score" => 0.42 }],
      "query" => "hello",
      "indexName" => "docs",
      "timeTakenMs" => 5
    )
    response = Struct.new(:code, :body).new("200", body)
    result = Moss::CloudQuery.parse_response(response, "hello")

    assert_equal 1, result.docs.length
    assert_equal "1", result.docs.first.id
    assert_in_delta 0.42, result.docs.first.score, 0.0001
    assert_equal 5, result.time_taken_ms
  end

  def test_parse_response_raises_http_error_on_non_2xx
    response = Struct.new(:code, :body).new("500", "boom")
    error = assert_raises(Moss::HTTPError) { Moss::CloudQuery.parse_response(response, "hello") }
    assert_equal 500, error.status_code
  end
end
