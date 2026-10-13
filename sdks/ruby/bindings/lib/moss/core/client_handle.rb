# frozen_string_literal: true

require "ffi"
require_relative "ffi"
require_relative "library"
require_relative "errors"
require_relative "marshalling"

module Moss
  module Core
    # Owns a single native `MossClient*` handle and serialises access to it.
    #
    # libmoss exposes one client type that backs manage, local-index and session
    # operations; ManageClient and IndexManager each wrap their own handle so
    # their locks stay independent (matching the Go bindings' two-handle model).
    #
    # The handle is freed by an ObjectSpace finalizer as a safety net, but
    # callers should prefer explicit #close for deterministic cleanup. The
    # finalizer closes over a shared state Hash (never over `self`) so it can run
    # without keeping the object alive.
    class ClientHandle
      def initialize(project_id, project_key)
        Library.ensure_attached!

        out = ::FFI::MemoryPointer.new(:pointer)
        Marshalling.check!(
          FFIBindings.moss_client_new(project_id.to_s, project_key.to_s, out)
        )

        @state = { ptr: out.read_pointer }
        @mutex = Mutex.new
        ObjectSpace.define_finalizer(self, self.class.finalizer(@state))
      end

      # Frees the native handle. Idempotent and safe to call from multiple
      # threads.
      def close
        @mutex.synchronize do
          ptr = @state[:ptr]
          return if ptr.nil? || ptr.null?

          FFIBindings.moss_client_free(ptr)
          @state[:ptr] = nil
        end
      end

      def closed?
        ptr = @state[:ptr]
        ptr.nil? || ptr.null?
      end

      # Runs the block with the raw handle under the mutex, raising if closed.
      def with_handle
        @mutex.synchronize do
          ptr = @state[:ptr]
          raise ClientClosedError if ptr.nil? || ptr.null?

          yield ptr
        end
      end

      def self.finalizer(state)
        proc do
          ptr = state[:ptr]
          if ptr && !ptr.null?
            FFIBindings.moss_client_free(ptr)
            state[:ptr] = nil
          end
        end
      end
    end
  end
end
