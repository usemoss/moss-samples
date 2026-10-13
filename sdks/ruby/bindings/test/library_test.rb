# frozen_string_literal: true

require_relative "test_helper"

class LibraryTest < Minitest::Test
  def test_default_basename_is_platform_appropriate
    assert_includes Moss::Core::Library::DEFAULT_BASENAME, "moss"
  end

  def test_env_library_path_takes_precedence
    with_env("MOSS_LIBRARY_PATH" => "/custom/path/libmoss.dylib") do
      assert_equal "/custom/path/libmoss.dylib", Moss::Core::Library.resolved_path
    end
  end

  def test_blank_env_is_ignored
    with_env("MOSS_LIBRARY_PATH" => "   ", "MOSS_LIB_DIR" => "") do
      assert_equal Moss::Core::Library::DEFAULT_BASENAME, Moss::Core::Library.resolved_path
    end
  end

  def test_value_objects_are_constructible
    doc = Moss::Core::DocumentInfo.new(id: "1", text: "hi")
    assert_equal "1", doc.id
    assert_nil doc.embedding

    result = Moss::Core::MutationResult.new(job_id: "j", index_name: "idx", doc_count: 2)
    assert_equal 2, result.doc_count
  end

  # Verifies the whole FFI mapping attaches against a real libmoss when one is
  # available (MOSS_LIB_DIR / MOSS_LIBRARY_PATH set). Skips otherwise so the
  # suite is green on machines without the C SDK.
  def test_attaches_and_reports_version_when_libmoss_present
    skip("libmoss not available") unless Moss::Core.available?

    version = Moss::Core.libmoss_sdk_version
    refute_nil version
    assert_match(/\A\d+\.\d+/, version)

    client = Moss::Core::ManageClient.new("dummy-project", "dummy-key")
    refute_nil client
    client.close
  end

  private

  def with_env(overrides)
    original = {}
    overrides.each do |key, value|
      original[key] = ENV.fetch(key, nil)
      ENV[key] = value
    end
    yield
  ensure
    original.each { |key, value| ENV[key] = value }
  end
end
