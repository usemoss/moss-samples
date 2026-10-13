# frozen_string_literal: true

require "json"
require "net/http"
require "uri"
require_relative "errors"
require_relative "models"

module Moss
  # Cloud query fallback used when an index is not loaded into the local runtime
  # (or when libmoss is unavailable entirely). Mirrors the Go SDK's queryCloud:
  # a single POST to the derived query endpoint. Alpha and metadata filters are
  # local-only; requesting them here raises UnsupportedQueryError.
  module CloudQuery
    module_function

    DEFAULT_TOP_K = 10

    def execute(query_url:, project_id:, project_key:, index_name:, query:, options:, http_open_timeout:,
                http_read_timeout:)
      raise ConfigurationError, "moss: query URL is not configured" if query_url.nil? || query_url.strip.empty?

      top_k = DEFAULT_TOP_K
      embedding = nil
      if options
        if options.alpha || (options.filter && !options.filter.empty?)
          raise UnsupportedQueryError,
                "moss: alpha and filter query options require a locally loaded index; call load_index first"
        end
        top_k = options.top_k if options.top_k&.positive?
        embedding = options.embedding if options.embedding && !options.embedding.empty?
      end

      payload = {
        query: query,
        indexName: index_name,
        projectId: project_id,
        projectKey: project_key,
        topK: top_k
      }
      payload[:queryEmbedding] = embedding if embedding

      response = post_json(query_url, payload, http_open_timeout, http_read_timeout)
      parse_response(response, query)
    end

    def post_json(url, payload, open_timeout, read_timeout)
      uri = URI.parse(url)
      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = (uri.scheme == "https")
      http.open_timeout = open_timeout
      http.read_timeout = read_timeout

      request = Net::HTTP::Post.new(uri.request_uri)
      request["Content-Type"] = "application/json"
      request.body = JSON.generate(payload)

      http.request(request)
    end

    def parse_response(response, query)
      code = response.code.to_i
      unless code >= 200 && code < 300
        body = response.body.to_s[0, 16 * 1024].strip
        raise HTTPError.new(status_code: code, body: body)
      end

      data = JSON.parse(response.body || "{}")
      docs = Array(data["docs"]).map do |doc|
        QueryResultDocument.new(
          id: doc["id"],
          text: doc["text"],
          metadata: doc["metadata"],
          score: doc["score"]
        )
      end

      SearchResult.new(
        docs: docs,
        query: data.fetch("query", query),
        index_name: data["indexName"],
        time_taken_ms: data["timeTakenMs"]
      )
    end
  end
end
