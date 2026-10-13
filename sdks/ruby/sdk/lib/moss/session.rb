# frozen_string_literal: true

require_relative "models"

module Moss
  # High-level wrapper around a native Moss::Core::Session. Build an index in
  # memory, query it locally, then push it to the cloud. Obtained via
  # Client#session.
  #
  #   session = client.session("scratch")
  #   session.add_documents([Moss::DocumentInfo.new(id: "1", text: "hello")])
  #   session.query("greeting")
  #   session.push_index
  #   session.close
  class Session
    def initialize(core_session)
      @core = core_session
    end

    def name
      @core.name
    end

    def doc_count
      @core.doc_count
    end

    def add_documents(documents, upsert: nil)
      options = upsert.nil? ? nil : Moss::Core::AddDocsOptions.new(upsert: upsert)
      result = @core.add_docs(to_core_documents(documents), options)
      { added: result.added, updated: result.updated }
    end
    alias add_docs add_documents

    def delete_documents(doc_ids)
      @core.delete_docs(Array(doc_ids).map(&:to_s))
    end
    alias delete_docs delete_documents

    def get_documents(doc_ids = nil)
      ids = doc_ids.nil? ? [] : Array(doc_ids).map(&:to_s)
      @core.get_docs(ids).map { |doc| to_document(doc) }
    end
    alias get_docs get_documents

    def query(query_text, embedding: nil, top_k: Moss::Core::DEFAULT_TOP_K,
              alpha: Moss::Core::DEFAULT_ALPHA, filter: nil)
      filter_json = filter && !filter.empty? ? JSON.generate(filter) : nil
      result = @core.query(
        query_text, embedding: embedding, top_k: top_k, alpha: alpha, filter_json: filter_json
      )
      to_search_result(result)
    end
    alias search query

    def load_index(index_name)
      @core.load_index(index_name)
    end

    def push_index
      result = @core.push_index
      MutationResult.new(job_id: result.job_id, index_name: result.index_name, doc_count: result.doc_count)
    end

    def close
      @core.close
    end

    private

    def to_core_documents(documents)
      documents.map do |doc|
        Moss::Core::DocumentInfo.new(
          id: doc.id.to_s,
          text: (doc.text || "").to_s,
          metadata: normalize_metadata(doc.metadata),
          embedding: doc.respond_to?(:embedding) ? doc.embedding : nil
        )
      end
    end

    def normalize_metadata(metadata)
      return nil if metadata.nil? || metadata.empty?

      metadata.each_with_object({}) { |(k, v), acc| acc[k.to_s] = v.to_s }
    end

    def to_document(core)
      DocumentInfo.new(id: core.id, text: core.text, metadata: core.metadata, embedding: core.embedding)
    end

    def to_search_result(core)
      docs = core.docs.map do |doc|
        QueryResultDocument.new(id: doc.id, text: doc.text, metadata: doc.metadata, score: doc.score)
      end
      SearchResult.new(docs: docs, query: core.query, index_name: core.index_name, time_taken_ms: core.time_taken_ms)
    end
  end
end
