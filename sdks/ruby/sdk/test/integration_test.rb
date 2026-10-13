# frozen_string_literal: true

require_relative "test_helper"

# End-to-end tests that hit the live Moss cloud + native libmoss runtime.
#
# They auto-skip unless BOTH of these hold, mirroring the other SDKs' E2E suites:
#   * MOSS_PROJECT_ID and MOSS_PROJECT_KEY are set
#   * libmoss is loadable (MOSS_LIB_DIR / MOSS_LIBRARY_PATH points at the C SDK)
#
# Run with, e.g.:
#   MOSS_LIB_DIR=/path/to/libmoss/lib \
#   DYLD_LIBRARY_PATH=/path/to/libmoss/lib \
#   MOSS_PROJECT_ID=... MOSS_PROJECT_KEY=... \
#   ruby -Itest -Ilib test/integration_test.rb
class IntegrationTest < Minitest::Test
  def setup
    unless credentials? && Moss::Core.available?
      skip("integration test skipped: set MOSS_PROJECT_ID/MOSS_PROJECT_KEY and make libmoss available")
    end

    @client = Moss::Client.new(poll_interval_seconds: 2)
    @index_name = "ruby-sdk-it-#{Process.pid}-#{rand(100_000)}"
  end

  def teardown
    return unless defined?(@client) && @client

    @client.unload_index(@index_name)
    @client.delete_index(@index_name)
  rescue StandardError
    # best-effort cleanup
  ensure
    @client&.close
  end

  def test_index_load_query_and_metadata_filter_round_trip
    docs = [
      Moss::DocumentInfo.new(id: "1", text: "Refunds are processed within five to seven business days.",
                             metadata: { "topic" => "refunds" }),
      Moss::DocumentInfo.new(id: "2", text: "Orders can be tracked from the account dashboard.",
                             metadata: { "topic" => "shipping" })
    ]

    create = @client.create_index(@index_name, docs)
    assert_equal 2, create.doc_count

    @client.load_index(@index_name)

    result = @client.query(@index_name, "how long do refunds take?", top_k: 3)
    refute_empty result.docs
    assert_equal "1", result.docs.first.id

    filtered = @client.query(
      @index_name, "how long do refunds take?",
      top_k: 3, filter: { "field" => "topic", "condition" => { "$eq" => "shipping" } }
    )
    assert(filtered.docs.all? { |doc| doc.metadata.nil? || doc.metadata["topic"] == "shipping" })
  end

  private

  def credentials?
    id = ENV["MOSS_PROJECT_ID"].to_s.strip
    key = ENV["MOSS_PROJECT_KEY"].to_s.strip
    !id.empty? && !key.empty?
  end
end
