# frozen_string_literal: true

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)
# Resolve the sibling bindings gem without Bundler so tests run via `ruby -Itest`.
$LOAD_PATH.unshift File.expand_path("../../bindings/lib", __dir__)

require "minitest/autorun"
require "moss"

module TestSupport
  # Temporarily replaces a singleton method, restoring it afterward. Avoids a
  # dependency on minitest/mock (not bundled with every minitest build).
  def self.with_stubbed_singleton(mod, name, replacement)
    original = mod.method(name)
    mod.singleton_class.send(:define_method, name, replacement)
    yield
  ensure
    mod.singleton_class.send(:define_method, name, original)
  end
end

module TestSupport
  # A fake ManageClient recording calls and returning canned results, used to
  # unit-test the high-level client without libmoss or live credentials.
  class FakeManageClient
    attr_reader :calls

    def initialize(job_status_sequence: nil)
      @calls = []
      @job_status_sequence = job_status_sequence
      @closed = false
    end

    def create_index(name, docs, model_id = nil)
      @calls << [:create_index, name, docs, model_id]
      Moss::Core::MutationResult.new(job_id: "job-1", index_name: name, doc_count: docs.length)
    end

    def add_docs(name, docs, options = nil)
      @calls << [:add_docs, name, docs, options]
      Moss::Core::MutationResult.new(job_id: "job-2", index_name: name, doc_count: docs.length)
    end

    def delete_docs(name, doc_ids)
      @calls << [:delete_docs, name, doc_ids]
      Moss::Core::MutationResult.new(job_id: "job-3", index_name: name, doc_count: doc_ids.length)
    end

    def get_job_status(job_id)
      @calls << [:get_job_status, job_id]
      status = @job_status_sequence&.shift || "completed"
      Moss::Core::JobStatusResponse.new(
        job_id: job_id, status: status, progress: 1.0, current_phase: nil,
        error: nil, created_at: "t0", updated_at: "t1", completed_at: "t1"
      )
    end

    def get_index(name)
      @calls << [:get_index, name]
      Moss::Core::IndexInfo.new(
        id: "idx-1", name: name, version: "1", status: "Ready", doc_count: 2,
        created_at: "t0", updated_at: "t1",
        model: Moss::Core::ModelRef.new(id: "moss-minilm", version: "1")
      )
    end

    def list_indexes
      @calls << [:list_indexes]
      [get_index("docs")]
    end

    def delete_index(name)
      @calls << [:delete_index, name]
      true
    end

    def get_docs(name, doc_ids = [])
      @calls << [:get_docs, name, doc_ids]
      [Moss::Core::DocumentInfo.new(id: "1", text: "hello", metadata: { "k" => "v" }, embedding: nil)]
    end

    def close
      @closed = true
    end

    def closed?
      @closed
    end
  end

  # A fake IndexManager with configurable loaded state.
  class FakeIndexManager
    attr_reader :calls

    def initialize(loaded: [])
      @calls = []
      @loaded = loaded.map(&:to_s)
    end

    def load_index(index_name, _options = nil)
      @calls << [:load_index, index_name]
      @loaded << index_name.to_s
      Moss::Core::IndexInfo.new(
        id: "idx", name: index_name.to_s, version: "1", status: "Ready", doc_count: 1,
        created_at: nil, updated_at: nil,
        model: Moss::Core::ModelRef.new(id: "moss-minilm", version: nil)
      )
    end

    def unload_index(index_name)
      @calls << [:unload_index, index_name]
      @loaded.delete(index_name.to_s)
      nil
    end

    def has_index?(index_name)
      @loaded.include?(index_name.to_s)
    end

    def load_query_model(_index_name)
      nil
    end

    def query(index_name, query_text, embedding: nil, top_k: nil, alpha: nil, filter_json: nil)
      @calls << [:query, index_name, query_text, embedding, top_k, alpha, filter_json]
      Moss::Core::SearchResult.new(
        docs: [Moss::Core::QueryResultDocument.new(id: "1", text: "hello", metadata: nil, score: 0.9)],
        query: query_text, index_name: index_name.to_s, time_taken_ms: 3
      )
    end

    def close; end
  end
end
