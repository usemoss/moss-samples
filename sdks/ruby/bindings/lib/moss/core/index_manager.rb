# frozen_string_literal: true

require "set"
require_relative "ffi"
require_relative "client_handle"
require_relative "marshalling"
require_relative "models"

module Moss
  module Core
    # Native-backed manager for the local index runtime: load/unload indexes and
    # run sub-10ms local queries against them. Mirrors the Go bindings'
    # IndexManager, including the loaded-index bookkeeping used by the SDK to
    # decide between a local query and the cloud fallback.
    class IndexManager
      DEFAULT_TOP_K = Core::DEFAULT_TOP_K
      DEFAULT_ALPHA = Core::DEFAULT_ALPHA

      def initialize(project_id, project_key)
        @handle = ClientHandle.new(project_id, project_key)
        @loaded = Set.new
        @loaded_mutex = Mutex.new
      end

      def close
        @handle.close
        @loaded_mutex.synchronize { @loaded.clear }
      end

      def load_index(index_name, options = nil)
        opts = Marshalling.build_load_index_options(options)
        out = ::FFI::MemoryPointer.new(:pointer)

        @handle.with_handle do |client|
          Marshalling.check!(
            FFIBindings.moss_client_load_index(client, index_name.to_s, opts.pointer, out)
          )
        end
        _retain(opts)

        struct = FFIBindings::IndexInfo.new(out.read_pointer)
        info = Marshalling.read_index_info(struct)
        FFIBindings.moss_free_index_info(struct)

        @loaded_mutex.synchronize { @loaded.add(index_name.to_s) }
        info
      end

      def unload_index(index_name)
        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_unload_index(client, index_name.to_s))
        end
        @loaded_mutex.synchronize { @loaded.delete(index_name.to_s) }
        nil
      end

      def has_index?(index_name)
        @loaded_mutex.synchronize { @loaded.include?(index_name.to_s) }
      end

      # libmoss loads bundled query models as part of load_index; kept for parity
      # with SDKs that expose explicit model loading.
      def load_query_model(_index_name)
        nil
      end

      def query(index_name, query_text, embedding: nil, top_k: DEFAULT_TOP_K,
                alpha: DEFAULT_ALPHA, filter_json: nil)
        opts = Marshalling.build_query_options(
          top_k: top_k, alpha: alpha, filter_json: filter_json, embedding: embedding
        )
        out = ::FFI::MemoryPointer.new(:pointer)

        @handle.with_handle do |client|
          Marshalling.check!(
            FFIBindings.moss_client_query(client, index_name.to_s, query_text.to_s, opts.pointer, out)
          )
        end
        _retain(opts)

        struct = FFIBindings::SearchResult.new(out.read_pointer)
        result = Marshalling.read_search_result(struct)
        FFIBindings.moss_free_search_result(struct)
        result
      end

      def refresh_index(index_name)
        out = ::FFI::MemoryPointer.new(:pointer)
        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_refresh_index(client, index_name.to_s, out))
        end

        struct = FFIBindings::RefreshResult.new(out.read_pointer)
        result = Marshalling.read_refresh_result(struct)
        FFIBindings.moss_free_refresh_result(struct)
        result
      end

      def get_index_info(index_name)
        out = ::FFI::MemoryPointer.new(:pointer)
        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_get_index(client, index_name.to_s, out))
        end

        struct = FFIBindings::IndexInfo.new(out.read_pointer)
        info = Marshalling.read_index_info(struct)
        FFIBindings.moss_free_index_info(struct)
        info
      end

      private

      def _retain(_allocation); end
    end
  end
end
