# frozen_string_literal: true

require_relative "ffi"
require_relative "models"
require_relative "errors"

module Moss
  module Core
    # Conversions between Ruby values and the native C structs, plus result-code
    # checking. Split out from the client classes so ownership rules live in one
    # place:
    #
    #   * "build_*" methods allocate C memory for INPUT and return an Allocation
    #     whose #retained array must stay referenced until the native call
    #     returns (FFI frees MemoryPointers once they are unreachable).
    #   * "read_*" methods COPY native OUTPUT into Ruby objects; the caller is
    #     then responsible for invoking the matching moss_free_* deallocator.
    module Marshalling
      module_function

      # Holds a primary pointer plus every child allocation that backs it, so a
      # single local reference keeps the whole graph alive across an FFI call.
      Allocation = Struct.new(:pointer, :retained)

      NULL = ::FFI::Pointer::NULL

      # Raises NativeError unless the code is OK, attaching moss_last_error text.
      def check!(code)
        return if code == FFIBindings::Result::OK

        message = read_string(FFIBindings.moss_last_error) || "libmoss call failed"
        raise NativeError.new(message, code)
      end

      # ---- reads (native -> Ruby, copying) ---------------------------------

      def read_string(ptr)
        return nil if ptr.nil? || ptr.null?

        ptr.read_string.force_encoding(Encoding::UTF_8)
      end

      def read_metadata(ptr, count)
        return nil if ptr.nil? || ptr.null? || count.zero?

        entry_size = FFIBindings::MetadataEntry.size
        result = {}
        count.times do |i|
          entry = FFIBindings::MetadataEntry.new(ptr + (i * entry_size))
          key = read_string(entry[:key])
          result[key] = read_string(entry[:value]) unless key.nil?
        end
        result
      end

      def read_embedding(ptr, dim)
        return nil if ptr.nil? || ptr.null? || dim.zero?

        ptr.read_array_of_float(dim)
      end

      def read_index_info(struct)
        model = struct[:model]
        Core::IndexInfo.new(
          id: read_string(struct[:id]),
          name: read_string(struct[:name]),
          version: read_string(struct[:version]),
          status: read_string(struct[:status]),
          doc_count: struct[:doc_count],
          created_at: read_string(struct[:created_at]),
          updated_at: read_string(struct[:updated_at]),
          model: Core::ModelRef.new(
            id: read_string(model[:id]),
            version: read_string(model[:version])
          )
        )
      end

      def read_documents(base_ptr, count)
        return [] if base_ptr.nil? || base_ptr.null? || count.zero?

        struct_size = FFIBindings::DocumentInfo.size
        Array.new(count) do |i|
          struct = FFIBindings::DocumentInfo.new(base_ptr + (i * struct_size))
          Core::DocumentInfo.new(
            id: read_string(struct[:id]),
            text: read_string(struct[:text]),
            metadata: read_metadata(struct[:metadata], struct[:metadata_count]),
            embedding: read_embedding(struct[:embedding], struct[:embedding_dim])
          )
        end
      end

      def read_index_info_list(base_ptr, count)
        return [] if base_ptr.nil? || base_ptr.null? || count.zero?

        struct_size = FFIBindings::IndexInfo.size
        Array.new(count) do |i|
          read_index_info(FFIBindings::IndexInfo.new(base_ptr + (i * struct_size)))
        end
      end

      def read_search_result(struct)
        docs = []
        base = struct[:docs]
        count = struct[:doc_count]
        unless base.null? || count.zero?
          doc_size = FFIBindings::QueryResultDoc.size
          count.times do |i|
            doc = FFIBindings::QueryResultDoc.new(base + (i * doc_size))
            docs << Core::QueryResultDocument.new(
              id: read_string(doc[:id]),
              text: read_string(doc[:text]),
              metadata: read_metadata(doc[:metadata], doc[:metadata_count]),
              score: doc[:score]
            )
          end
        end

        Core::SearchResult.new(
          docs: docs,
          query: read_string(struct[:query]),
          index_name: read_string(struct[:index_name]),
          time_taken_ms: struct[:time_taken_ms]
        )
      end

      def read_job_status(struct)
        Core::JobStatusResponse.new(
          job_id: read_string(struct[:job_id]),
          status: read_string(struct[:status]),
          progress: struct[:progress],
          current_phase: read_string(struct[:current_phase]),
          error: read_string(struct[:error]),
          created_at: read_string(struct[:created_at]),
          updated_at: read_string(struct[:updated_at]),
          completed_at: read_string(struct[:completed_at])
        )
      end

      def read_mutation_result(struct)
        Core::MutationResult.new(
          job_id: read_string(struct[:job_id]),
          index_name: read_string(struct[:index_name]),
          doc_count: struct[:doc_count]
        )
      end

      def read_refresh_result(struct)
        Core::RefreshResult.new(
          index_name: read_string(struct[:index_name]),
          previous_updated_at: read_string(struct[:previous_updated_at]),
          new_updated_at: read_string(struct[:new_updated_at]),
          was_updated: struct[:was_updated]
        )
      end

      def read_push_index_result(struct)
        Core::PushIndexResult.new(
          job_id: read_string(struct[:job_id]),
          index_name: read_string(struct[:index_name]),
          doc_count: struct[:doc_count],
          status: read_string(struct[:status])
        )
      end

      # ---- builds (Ruby -> native, caller retains until the call returns) ---

      def mem_string(value)
        bytes = value.to_s.b
        ptr = ::FFI::MemoryPointer.new(:char, bytes.bytesize + 1) # zero-filled -> NUL terminator
        ptr.put_bytes(0, bytes)
        ptr
      end

      def mem_floats(values)
        ptr = ::FFI::MemoryPointer.new(:float, values.length)
        ptr.write_array_of_float(values.map(&:to_f))
        ptr
      end

      def build_documents(docs)
        retained = []
        count = docs.length
        return Allocation.new(NULL, retained) if count.zero?

        array = ::FFI::MemoryPointer.new(FFIBindings::DocumentInfo, count)
        retained << array
        struct_size = FFIBindings::DocumentInfo.size

        docs.each_with_index do |doc, i|
          entry = FFIBindings::DocumentInfo.new(array + (i * struct_size))

          id_ptr = mem_string(doc.id)
          text_ptr = mem_string(doc.text)
          retained << id_ptr << text_ptr
          entry[:id] = id_ptr
          entry[:text] = text_ptr

          apply_metadata(entry, doc.metadata, retained)
          apply_embedding(entry, doc.embedding, retained)
        end

        Allocation.new(array, retained)
      end

      def build_string_array(values)
        retained = []
        count = values.length
        return Allocation.new(NULL, retained) if count.zero?

        array = ::FFI::MemoryPointer.new(:pointer, count)
        retained << array
        values.each_with_index do |value, i|
          str_ptr = mem_string(value)
          retained << str_ptr
          array.put_pointer(i * ::FFI::Pointer.size, str_ptr)
        end

        Allocation.new(array, retained)
      end

      # Builds a MossQueryOptions struct. Returns an Allocation whose pointer is
      # the struct (or NULL when no options are provided).
      def build_query_options(top_k:, alpha:, filter_json:, embedding:)
        retained = []
        opts = FFIBindings::QueryOptions.new
        retained << opts

        opts[:top_k] = top_k
        opts[:alpha] = alpha

        if filter_json
          filter_ptr = mem_string(filter_json)
          retained << filter_ptr
          opts[:filter_json] = filter_ptr
        else
          opts[:filter_json] = NULL
        end

        if embedding && !embedding.empty?
          emb_ptr = mem_floats(embedding)
          retained << emb_ptr
          opts[:embedding] = emb_ptr
          opts[:embedding_dim] = embedding.length
        else
          opts[:embedding] = NULL
          opts[:embedding_dim] = 0
        end

        Allocation.new(opts.to_ptr, retained)
      end

      # Option-struct builders. Each returns an Allocation whose #retained array
      # keeps the FFI::Struct (and any backing strings) referenced for the
      # duration of the native call, and whose #pointer is NULL when no options
      # apply. Callers must keep the Allocation referenced until the call
      # returns (see the _retain sinks in the client classes).

      def build_mutation_options(options)
        return Allocation.new(NULL, []) if options.nil? || options.upsert.nil?

        struct = FFIBindings::MutationOptions.new
        struct[:upsert] = options.upsert ? true : false
        Allocation.new(struct.to_ptr, [struct])
      end

      def build_add_docs_options(options)
        return Allocation.new(NULL, []) if options.nil? || options.upsert.nil?

        struct = FFIBindings::AddDocsOptions.new
        struct[:upsert] = options.upsert ? true : false
        Allocation.new(struct.to_ptr, [struct])
      end

      def build_load_index_options(options)
        return Allocation.new(NULL, []) if options.nil?

        struct = FFIBindings::LoadIndexOptions.new
        struct[:auto_refresh] = options.auto_refresh ? true : false
        struct[:polling_interval_secs] = options.polling_interval_secs.to_i
        Allocation.new(struct.to_ptr, [struct])
      end

      def build_session_options(options)
        model_id = options&.model_id
        return Allocation.new(NULL, []) if model_id.nil?

        model_ptr = mem_string(model_id)
        struct = FFIBindings::SessionOptions.new
        struct[:model_id] = model_ptr
        Allocation.new(struct.to_ptr, [struct, model_ptr])
      end

      def apply_metadata(entry, metadata, retained)
        if metadata.nil? || metadata.empty?
          entry[:metadata] = NULL
          entry[:metadata_count] = 0
          return
        end

        array = ::FFI::MemoryPointer.new(FFIBindings::MetadataEntry, metadata.length)
        retained << array
        entry_size = FFIBindings::MetadataEntry.size

        metadata.each_with_index do |(key, value), j|
          meta = FFIBindings::MetadataEntry.new(array + (j * entry_size))
          key_ptr = mem_string(key)
          value_ptr = mem_string(value)
          retained << key_ptr << value_ptr
          meta[:key] = key_ptr
          meta[:value] = value_ptr
        end

        entry[:metadata] = array
        entry[:metadata_count] = metadata.length
      end

      def apply_embedding(entry, embedding, retained)
        if embedding.nil? || embedding.empty?
          entry[:embedding] = NULL
          entry[:embedding_dim] = 0
          return
        end

        emb_ptr = mem_floats(embedding)
        retained << emb_ptr
        entry[:embedding] = emb_ptr
        entry[:embedding_dim] = embedding.length
      end
    end
  end
end
