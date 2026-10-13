# frozen_string_literal: true

require_relative "core/version"
require_relative "core/errors"
require_relative "core/models"
require_relative "core/ffi"
require_relative "core/library"
require_relative "core/marshalling"
require_relative "core/client_handle"
require_relative "core/manage_client"
require_relative "core/index_manager"
require_relative "core/session"

module Moss
  # Moss::Core is the native binding layer: a thin FFI wrapper over the prebuilt
  # `libmoss` C SDK. It exposes ManageClient (cloud mutations + reads),
  # IndexManager (local index runtime + query) and Session (ephemeral in-memory
  # indexes). The high-level `moss` gem builds its ergonomic client on top of
  # these primitives.
  #
  # Requiring this file never touches the filesystem — libmoss is attached
  # lazily on first client construction (see Moss::Core::Library). Use
  # Moss::Core.available? to check whether the native runtime is present without
  # raising.
  module Core
    module_function

    # Returns the libmoss SDK version string reported by the loaded native
    # library, or nil when libmoss is unavailable.
    def libmoss_sdk_version
      return nil unless Library.available?

      Marshalling.read_string(FFIBindings.moss_sdk_version)
    end

    # True when libmoss can be loaded in this process.
    def available?
      Library.available?
    end
  end
end
