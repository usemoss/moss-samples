# frozen_string_literal: true

require "ffi"
require_relative "ffi"
require_relative "errors"

module Moss
  module Core
    # Locates and attaches the native `libmoss` shared library exactly once.
    #
    # Resolution order:
    #   1. ENV["MOSS_LIBRARY_PATH"]  — absolute path to the shared library file
    #   2. ENV["MOSS_LIB_DIR"]       — directory containing lib{moss}.{dylib,so,dll}
    #   3. the platform default name — resolved via the system loader search path
    #
    # Attaching by absolute path (options 1 and 2) is preferred on macOS: the
    # prebuilt `libmoss.dylib` ships with a build-server install name baked in,
    # and dlopen'ing the file directly sidesteps the need for DYLD_LIBRARY_PATH.
    module Library
      module_function

      DEFAULT_BASENAME = "#{::FFI::Platform::LIBPREFIX}moss.#{::FFI::Platform::LIBSUFFIX}".freeze

      # Returns the resolved shared-library path (absolute when derived from env),
      # or the bare platform basename to let the system loader search for it.
      def resolved_path
        explicit = env_value("MOSS_LIBRARY_PATH")
        return explicit if explicit

        dir = env_value("MOSS_LIB_DIR")
        if dir
          candidate = File.join(dir, DEFAULT_BASENAME)
          return candidate if File.exist?(candidate)

          # Fall back to any lib{moss}.* in the directory (e.g. versioned names).
          match = Dir.glob(File.join(dir, "#{::FFI::Platform::LIBPREFIX}moss.*")).first
          return match if match
        end

        DEFAULT_BASENAME
      end

      # Attaches libmoss on first call; memoized thereafter. Raises
      # BindingsUnavailableError (not a raw FFI/LoadError) when the library is
      # missing so callers can branch on a single, documented error type.
      def ensure_attached!
        return true if @attached

        @mutex ||= Mutex.new
        @mutex.synchronize do
          return true if @attached

          begin
            FFIBindings.attach!(resolved_path)
            @attached = true
          rescue LoadError, ::FFI::NotFoundError => e
            raise BindingsUnavailableError, "#{BindingsUnavailableError::DEFAULT_MESSAGE} (#{e.message})"
          end
        end
        @attached
      end

      # True when libmoss can be loaded in this process. Never raises — intended
      # for the SDK's "fall back to cloud query" decision.
      def available?
        ensure_attached!
      rescue BindingsUnavailableError
        false
      end

      # Test/reset hook: forget the memoized attachment state.
      def reset!
        @attached = false
      end

      def env_value(key)
        value = ENV.fetch(key, nil)
        return nil if value.nil?

        stripped = value.strip
        stripped.empty? ? nil : stripped
      end
    end
  end
end
