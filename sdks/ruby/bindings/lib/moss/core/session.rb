# frozen_string_literal: true

require "ffi"
require_relative "ffi"
require_relative "marshalling"
require_relative "models"
require_relative "errors"

module Moss
  module Core
    # Native-backed ephemeral session: build and query an index in memory, then
    # push it to the cloud. Sessions are created via ManageClient#session and
    # hold a reference to their owner so the underlying native client outlives
    # them. The MossSession* handle is freed by #close or an ObjectSpace
    # finalizer (which closes over a state Hash, never over `self`).
    class Session
      def initialize(ptr, owner:)
        @owner = owner
        @state = { ptr: ptr }
        @mutex = Mutex.new
        ObjectSpace.define_finalizer(self, self.class.finalizer(@state))
      end

      def name
        with_handle do |session|
          Marshalling.read_string(FFIBindings.moss_session_name(session))
        end
      end

      def doc_count
        with_handle { |session| FFIBindings.moss_session_doc_count(session) }
      end

      def add_docs(docs, options = nil)
        input = Marshalling.build_documents(docs)
        opts = Marshalling.build_add_docs_options(options)
        added = ::FFI::MemoryPointer.new(:size_t)
        updated = ::FFI::MemoryPointer.new(:size_t)

        with_handle do |session|
          Marshalling.check!(
            FFIBindings.moss_session_add_docs(
              session, input.pointer, docs.length, opts.pointer, added, updated
            )
          )
        end
        _retain(input)
        _retain(opts)

        Core::SessionAddResult.new(added: added.read(:size_t), updated: updated.read(:size_t))
      end

      def delete_docs(doc_ids)
        ids = Marshalling.build_string_array(doc_ids)
        deleted = ::FFI::MemoryPointer.new(:size_t)

        with_handle do |session|
          Marshalling.check!(
            FFIBindings.moss_session_delete_docs(session, ids.pointer, doc_ids.length, deleted)
          )
        end
        _retain(ids)

        deleted.read(:size_t)
      end

      def get_docs(doc_ids = [])
        ids = Marshalling.build_string_array(doc_ids)
        out = ::FFI::MemoryPointer.new(:pointer)
        count_ptr = ::FFI::MemoryPointer.new(:size_t)

        with_handle do |session|
          Marshalling.check!(
            FFIBindings.moss_session_get_docs(session, ids.pointer, doc_ids.length, out, count_ptr)
          )
        end
        _retain(ids)

        base = out.read_pointer
        count = count_ptr.read(:size_t)
        result = Marshalling.read_documents(base, count)
        FFIBindings.moss_free_documents(base, count) unless base.null?
        result
      end

      def query(query_text, embedding: nil, top_k: Core::DEFAULT_TOP_K,
                alpha: Core::DEFAULT_ALPHA, filter_json: nil)
        opts = Marshalling.build_query_options(
          top_k: top_k, alpha: alpha, filter_json: filter_json, embedding: embedding
        )
        out = ::FFI::MemoryPointer.new(:pointer)

        with_handle do |session|
          Marshalling.check!(
            FFIBindings.moss_session_query(session, query_text.to_s, opts.pointer, out)
          )
        end
        _retain(opts)

        struct = FFIBindings::SearchResult.new(out.read_pointer)
        result = Marshalling.read_search_result(struct)
        FFIBindings.moss_free_search_result(struct)
        result
      end

      def load_index(index_name)
        count_ptr = ::FFI::MemoryPointer.new(:size_t)
        with_handle do |session|
          Marshalling.check!(
            FFIBindings.moss_session_load_index(session, index_name.to_s, count_ptr)
          )
        end
        count_ptr.read(:size_t)
      end

      def push_index
        out = ::FFI::MemoryPointer.new(:pointer)
        with_handle do |session|
          Marshalling.check!(FFIBindings.moss_session_push_index(session, out))
        end

        struct = FFIBindings::PushIndexResult.new(out.read_pointer)
        result = Marshalling.read_push_index_result(struct)
        FFIBindings.moss_free_push_index_result(struct)
        result
      end

      def close
        @mutex.synchronize do
          ptr = @state[:ptr]
          return if ptr.nil? || ptr.null?

          FFIBindings.moss_session_free(ptr)
          @state[:ptr] = nil
        end
      end

      def self.finalizer(state)
        proc do
          ptr = state[:ptr]
          if ptr && !ptr.null?
            FFIBindings.moss_session_free(ptr)
            state[:ptr] = nil
          end
        end
      end

      private

      def with_handle
        @mutex.synchronize do
          ptr = @state[:ptr]
          raise ClientClosedError, "moss-core: session is closed" if ptr.nil? || ptr.null?

          yield ptr
        end
      end

      def _retain(_allocation); end
    end
  end
end
