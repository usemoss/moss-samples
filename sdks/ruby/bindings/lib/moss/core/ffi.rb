# frozen_string_literal: true

require "ffi"

module Moss
  module Core
    # Raw FFI mapping of the `libmoss` C ABI (see include/libmoss.h in the
    # `c-sdk` release). This module is a 1:1 translation of the header and
    # contains no higher-level logic — that lives in ManageClient / IndexManager
    # / Session. The library is attached lazily by Moss::Core::Library so that a
    # missing `libmoss` degrades to BindingsUnavailableError instead of a load
    # crash at require time.
    module FFIBindings
      extend ::FFI::Library

      # Result codes returned by every fallible `moss_*` function.
      module Result
        OK                  = 0
        ERR_NULL_POINTER    = -1
        ERR_INVALID_ARG     = -2
        ERR_CLOUD           = -3
        ERR_INDEX_NOT_FOUND = -4
        ERR_MODEL           = -5
        ERR_IO              = -6
        ERR_INTERNAL        = -7
      end

      # typedef struct MossMetadataEntry { char *key; char *value; }
      class MetadataEntry < ::FFI::Struct
        layout :key, :pointer,
               :value, :pointer
      end

      # typedef struct MossDocumentInfo { ... }
      class DocumentInfo < ::FFI::Struct
        layout :id, :pointer,
               :text, :pointer,
               :metadata, :pointer,        # MossMetadataEntry*
               :metadata_count, :size_t,
               :embedding, :pointer,       # float*
               :embedding_dim, :size_t
      end

      # typedef struct MossMutationResult { ... }
      class MutationResult < ::FFI::Struct
        layout :job_id, :pointer,
               :index_name, :pointer,
               :doc_count, :size_t
      end

      # typedef struct MossMutationOptions { bool upsert; }
      class MutationOptions < ::FFI::Struct
        layout :upsert, :bool
      end

      # typedef struct MossModelRef { char *id; char *version; }
      class ModelRef < ::FFI::Struct
        layout :id, :pointer,
               :version, :pointer
      end

      # typedef struct MossIndexInfo { ... MossModelRef model; }
      class IndexInfo < ::FFI::Struct
        layout :id, :pointer,
               :name, :pointer,
               :version, :pointer,
               :status, :pointer,
               :doc_count, :size_t,
               :created_at, :pointer,
               :updated_at, :pointer,
               :model, ModelRef # nested by value
      end

      # typedef struct MossJobStatusResponse { ... }
      class JobStatusResponse < ::FFI::Struct
        layout :job_id, :pointer,
               :status, :pointer,
               :progress, :double,
               :current_phase, :pointer,
               :error, :pointer,
               :created_at, :pointer,
               :updated_at, :pointer,
               :completed_at, :pointer
      end

      # typedef struct MossLoadIndexOptions { bool auto_refresh; uint64_t polling_interval_secs; }
      class LoadIndexOptions < ::FFI::Struct
        layout :auto_refresh, :bool,
               :polling_interval_secs, :uint64
      end

      # typedef struct MossQueryOptions { ... }
      class QueryOptions < ::FFI::Struct
        layout :top_k, :size_t,
               :alpha, :float,
               :filter_json, :pointer,     # const char*
               :embedding, :pointer,       # const float*
               :embedding_dim, :size_t
      end

      # typedef struct MossQueryResultDoc { ... float score; }
      class QueryResultDoc < ::FFI::Struct
        layout :id, :pointer,
               :text, :pointer,
               :metadata, :pointer, # MossMetadataEntry*
               :metadata_count, :size_t,
               :score, :float
      end

      # typedef struct MossSearchResult { ... }
      class SearchResult < ::FFI::Struct
        layout :docs, :pointer, # MossQueryResultDoc*
               :doc_count, :size_t,
               :query, :pointer,
               :index_name, :pointer,
               :time_taken_ms, :uint64
      end

      # typedef struct MossRefreshResult { ... }
      class RefreshResult < ::FFI::Struct
        layout :index_name, :pointer,
               :previous_updated_at, :pointer,
               :new_updated_at, :pointer,
               :was_updated, :bool
      end

      # typedef struct MossSessionOptions { const char *model_id; }
      class SessionOptions < ::FFI::Struct
        layout :model_id, :pointer
      end

      # typedef struct MossAddDocsOptions { bool upsert; }
      class AddDocsOptions < ::FFI::Struct
        layout :upsert, :bool
      end

      # typedef struct MossPushIndexResult { ... }
      class PushIndexResult < ::FFI::Struct
        layout :job_id, :pointer,
               :index_name, :pointer,
               :doc_count, :size_t,
               :status, :pointer
      end

      # Attaches every `moss_*` symbol against a resolved libmoss path. Called
      # once by Moss::Core::Library. Kept as a method (rather than top-level
      # attach_function calls) so that require'ing this file never touches the
      # filesystem — attachment is deferred until a client is constructed.
      def self.attach!(library_path)
        ffi_lib library_path

        # --- lifecycle -------------------------------------------------------
        attach_function :moss_sdk_version, [], :pointer
        attach_function :moss_last_error, [], :pointer
        attach_function :moss_client_new, %i[string string pointer], :int
        attach_function :moss_client_free, [:pointer], :void

        # --- manage (cloud mutations + reads) --------------------------------
        attach_function :moss_client_create_index,
                        %i[pointer string pointer size_t string pointer], :int
        attach_function :moss_client_add_docs,
                        %i[pointer string pointer size_t pointer pointer], :int
        attach_function :moss_client_delete_docs,
                        %i[pointer string pointer size_t pointer], :int
        attach_function :moss_client_delete_index, %i[pointer string pointer], :int
        attach_function :moss_client_get_index, %i[pointer string pointer], :int
        attach_function :moss_client_list_indexes, %i[pointer pointer pointer], :int
        attach_function :moss_client_get_docs,
                        %i[pointer string pointer size_t pointer pointer], :int
        attach_function :moss_client_get_job_status, %i[pointer string pointer], :int

        # --- local index runtime --------------------------------------------
        attach_function :moss_client_load_index, %i[pointer string pointer pointer], :int
        attach_function :moss_client_unload_index, %i[pointer string], :int
        attach_function :moss_client_query,
                        %i[pointer string string pointer pointer], :int
        attach_function :moss_client_refresh_index, %i[pointer string pointer], :int

        # --- sessions --------------------------------------------------------
        attach_function :moss_client_session, %i[pointer string pointer pointer], :int
        attach_function :moss_session_free, [:pointer], :void
        attach_function :moss_session_name, [:pointer], :pointer
        attach_function :moss_session_doc_count, [:pointer], :size_t
        attach_function :moss_session_add_docs,
                        %i[pointer pointer size_t pointer pointer pointer], :int
        attach_function :moss_session_delete_docs,
                        %i[pointer pointer size_t pointer], :int
        attach_function :moss_session_get_docs,
                        %i[pointer pointer size_t pointer pointer], :int
        attach_function :moss_session_query, %i[pointer string pointer pointer], :int
        attach_function :moss_session_load_index, %i[pointer string pointer], :int
        attach_function :moss_session_push_index, %i[pointer pointer], :int

        # --- deallocators (must pair with the allocating call) ---------------
        attach_function :moss_free_string, [:pointer], :void
        attach_function :moss_free_documents, %i[pointer size_t], :void
        attach_function :moss_free_search_result, [:pointer], :void
        attach_function :moss_free_index_info, [:pointer], :void
        attach_function :moss_free_index_info_list, %i[pointer size_t], :void
        attach_function :moss_free_mutation_result, [:pointer], :void
        attach_function :moss_free_push_index_result, [:pointer], :void
        attach_function :moss_free_job_status_response, [:pointer], :void
        attach_function :moss_free_refresh_result, [:pointer], :void
      end
    end
  end
end
