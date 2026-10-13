# frozen_string_literal: true

module Moss
  module Core
    # Tracks the libmoss C ABI this binding targets. Bump alongside the pinned
    # `c-sdk` release in Moss::Core::LIBMOSS_VERSION.
    VERSION = "0.9.0"

    # The libmoss C SDK release these bindings are generated against.
    LIBMOSS_VERSION = "0.9.0"
  end
end
