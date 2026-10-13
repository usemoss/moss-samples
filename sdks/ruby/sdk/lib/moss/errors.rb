# frozen_string_literal: true

module Moss
  # Base class for every error raised by the Moss Ruby SDK.
  class Error < StandardError; end

  # Raised when the client is missing required configuration (project id/key or
  # a query URL for the cloud fallback).
  class ConfigurationError < Error; end

  # Raised for invalid arguments before a request is issued.
  class ArgumentError < Error; end

  # Raised when a mutation job ends in a failed state, or polling exhausts its
  # retry budget.
  class JobError < Error; end

  # Raised when the cloud query fallback returns a non-2xx response.
  class HTTPError < Error
    attr_reader :status_code, :body

    def initialize(status_code:, body: nil)
      @status_code = status_code
      @body = body
      message = "moss: cloud query failed with status #{status_code}"
      message += ": #{body}" if body && !body.empty?
      super(message)
    end
  end

  # Raised when a query uses local-only options (alpha/filter) but no index is
  # loaded locally and the request would fall back to the cloud API.
  class UnsupportedQueryError < Error; end
end
