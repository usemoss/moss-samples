# frozen_string_literal: true

require_relative "ffi"
require_relative "client_handle"
require_relative "marshalling"
require_relative "models"
require_relative "session"

module Moss
  module Core
    # Native-backed client for cloud mutations and reads. Every method routes
    # through libmoss and returns the plain-Ruby value objects from
    # Moss::Core::models. Raises Moss::Core::BindingsUnavailableError at
    # construction if libmoss cannot be loaded.
    class ManageClient
      def initialize(project_id, project_key)
        @handle = ClientHandle.new(project_id, project_key)
      end

      def close
        @handle.close
      end

      def create_index(name, docs, model_id = nil)
        input = Marshalling.build_documents(docs)
        out = ::FFI::MemoryPointer.new(:pointer)

        @handle.with_handle do |client|
          Marshalling.check!(
            FFIBindings.moss_client_create_index(
              client, name.to_s, input.pointer, docs.length, model_id, out
            )
          )
        end
        _retain(input)

        read_and_free_mutation_result(out)
      end

      def add_docs(name, docs, options = nil)
        input = Marshalling.build_documents(docs)
        opts = Marshalling.build_mutation_options(options)
        out = ::FFI::MemoryPointer.new(:pointer)

        @handle.with_handle do |client|
          Marshalling.check!(
            FFIBindings.moss_client_add_docs(
              client, name.to_s, input.pointer, docs.length, opts.pointer, out
            )
          )
        end
        _retain(input)
        _retain(opts)

        read_and_free_mutation_result(out)
      end

      def delete_docs(name, doc_ids)
        ids = Marshalling.build_string_array(doc_ids)
        out = ::FFI::MemoryPointer.new(:pointer)

        @handle.with_handle do |client|
          Marshalling.check!(
            FFIBindings.moss_client_delete_docs(
              client, name.to_s, ids.pointer, doc_ids.length, out
            )
          )
        end
        _retain(ids)

        read_and_free_mutation_result(out)
      end

      def get_job_status(job_id)
        out = ::FFI::MemoryPointer.new(:pointer)
        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_get_job_status(client, job_id.to_s, out))
        end

        struct = FFIBindings::JobStatusResponse.new(out.read_pointer)
        result = Marshalling.read_job_status(struct)
        FFIBindings.moss_free_job_status_response(struct)
        result
      end

      def get_index(name)
        out = ::FFI::MemoryPointer.new(:pointer)
        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_get_index(client, name.to_s, out))
        end
        read_and_free_index_info(out)
      end

      def list_indexes
        out = ::FFI::MemoryPointer.new(:pointer)
        count_ptr = ::FFI::MemoryPointer.new(:size_t)

        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_list_indexes(client, out, count_ptr))
        end

        base = out.read_pointer
        count = count_ptr.read(:size_t)
        result = Marshalling.read_index_info_list(base, count)
        FFIBindings.moss_free_index_info_list(base, count) unless base.null?
        result
      end

      def delete_index(name)
        deleted = ::FFI::MemoryPointer.new(:bool)
        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_delete_index(client, name.to_s, deleted))
        end
        deleted.read(:bool)
      end

      def get_docs(name, doc_ids = [])
        ids = Marshalling.build_string_array(doc_ids)
        out = ::FFI::MemoryPointer.new(:pointer)
        count_ptr = ::FFI::MemoryPointer.new(:size_t)

        @handle.with_handle do |client|
          Marshalling.check!(
            FFIBindings.moss_client_get_docs(
              client, name.to_s, ids.pointer, doc_ids.length, out, count_ptr
            )
          )
        end
        _retain(ids)

        base = out.read_pointer
        count = count_ptr.read(:size_t)
        result = Marshalling.read_documents(base, count)
        FFIBindings.moss_free_documents(base, count) unless base.null?
        result
      end

      # Opens a session backed by this client. Keeps the ManageClient referenced
      # so the underlying native handle outlives the session.
      def session(name, options = nil)
        opts = Marshalling.build_session_options(options)
        out = ::FFI::MemoryPointer.new(:pointer)

        @handle.with_handle do |client|
          Marshalling.check!(FFIBindings.moss_client_session(client, name.to_s, opts.pointer, out))
        end
        _retain(opts)

        Session.new(out.read_pointer, owner: self)
      end

      private

      def read_and_free_mutation_result(out)
        struct = FFIBindings::MutationResult.new(out.read_pointer)
        result = Marshalling.read_mutation_result(struct)
        FFIBindings.moss_free_mutation_result(struct)
        result
      end

      def read_and_free_index_info(out)
        struct = FFIBindings::IndexInfo.new(out.read_pointer)
        result = Marshalling.read_index_info(struct)
        FFIBindings.moss_free_index_info(struct)
        result
      end

      # No-op reference sink documenting that the input allocation must survive
      # until the native call above has returned.
      def _retain(_allocation); end
    end
  end
end
