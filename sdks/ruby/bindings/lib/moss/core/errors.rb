# frozen_string_literal: true

module Moss
  module Core
    # Base class for every error raised by the native binding layer.
    class Error < StandardError; end

    # Raised when `libmoss` cannot be located or attached. The high-level SDK
    # treats this as a signal to fall back to the cloud query API, mirroring the
    # Go SDK's `ErrBindingsUnavailable` behaviour.
    class BindingsUnavailableError < Error
      DEFAULT_MESSAGE =
        "moss-core: libmoss is unavailable. Download the libmoss C SDK release " \
        "and point MOSS_LIB_DIR (or MOSS_LIBRARY_PATH) at it. See " \
        "https://github.com/usemoss/moss/releases (c-sdk)."

      def initialize(message = DEFAULT_MESSAGE)
        super
      end
    end

    # Raised after a client/session handle has been freed.
    class ClientClosedError < Error
      def initialize(message = "moss-core: client is closed")
        super
      end
    end

    # Raised when a `moss_*` call returns a non-OK result code. Carries the
    # numeric code and the thread-local message from `moss_last_error`.
    class NativeError < Error
      attr_reader :code

      def initialize(message, code)
        @code = code
        super("moss-core: #{message} (code #{code})")
      end
    end
  end
end
