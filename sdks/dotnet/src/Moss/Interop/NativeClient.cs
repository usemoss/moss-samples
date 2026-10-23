using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Moss.Interop;

/// <summary>
/// Thin, synchronous wrapper over the native <c>libmoss</c> client handle. It
/// owns the <c>MossClient*</c>, marshals managed inputs, checks status codes,
/// reads outputs back into managed models, and releases every native
/// allocation. All public methods are serialized behind a lock, mirroring the
/// per-client mutex the Go bindings use.
/// </summary>
internal sealed class NativeClient : IDisposable
{
    private readonly object _gate = new();
    private readonly MossClientHandle _handle;

    public NativeClient(string projectId, string projectKey)
    {
        using var arena = new NativeArena();
        Check(NativeMethods.moss_client_new(arena.String(projectId), arena.String(projectKey), out IntPtr raw));
        if (raw == IntPtr.Zero)
            throw new MossException(-1, "moss_client_new returned a null client");
        _handle = new MossClientHandle();
        _handle.SetRawHandle(raw);
    }

    // ---- Management ------------------------------------------------------

    public MutationResult CreateIndex(string name, IReadOnlyList<DocumentInfo> docs, string? modelId)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            IntPtr docsPtr = BuildDocuments(arena, docs);
            Check(NativeMethods.moss_client_create_index(
                _handle, arena.String(name), docsPtr, (nuint)docs.Count, arena.String(modelId), out IntPtr outPtr));
            return ReadMutationResult(outPtr);
        }
    }

    public MutationResult AddDocs(string name, IReadOnlyList<DocumentInfo> docs, MutationOptions? options)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            IntPtr docsPtr = BuildDocuments(arena, docs);
            IntPtr optsPtr = IntPtr.Zero;
            if (options?.Upsert is bool upsert)
            {
                var native = new MossMutationOptions { upsert = upsert };
                optsPtr = arena.StructArray(new[] { native });
            }
            Check(NativeMethods.moss_client_add_docs(
                _handle, arena.String(name), docsPtr, (nuint)docs.Count, optsPtr, out IntPtr outPtr));
            return ReadMutationResult(outPtr);
        }
    }

    public MutationResult DeleteDocs(string name, IReadOnlyList<string> docIds)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_delete_docs(
                _handle, arena.String(name), arena.StringArray(docIds), (nuint)docIds.Count, out IntPtr outPtr));
            return ReadMutationResult(outPtr);
        }
    }

    public IReadOnlyList<DocumentInfo> GetDocs(string name, IReadOnlyList<string> docIds)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_get_docs(
                _handle, arena.String(name), arena.StringArray(docIds), (nuint)docIds.Count,
                out IntPtr outDocs, out nuint count));
            try
            {
                return ReadDocuments(outDocs, count);
            }
            finally
            {
                NativeMethods.moss_free_documents(outDocs, count);
            }
        }
    }

    public IndexInfo GetIndex(string name)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_get_index(_handle, arena.String(name), out IntPtr outPtr));
            try
            {
                return ReadIndexInfo(Marshal.PtrToStructure<MossIndexInfo>(outPtr));
            }
            finally
            {
                NativeMethods.moss_free_index_info(outPtr);
            }
        }
    }

    public IReadOnlyList<IndexInfo> ListIndexes()
    {
        lock (_gate)
        {
            EnsureOpen();
            Check(NativeMethods.moss_client_list_indexes(_handle, out IntPtr outPtr, out nuint count));
            try
            {
                int size = Marshal.SizeOf<MossIndexInfo>();
                var result = new List<IndexInfo>((int)count);
                for (nuint i = 0; i < count; i++)
                {
                    var native = Marshal.PtrToStructure<MossIndexInfo>(outPtr + (int)i * size);
                    result.Add(ReadIndexInfo(native));
                }
                return result;
            }
            finally
            {
                NativeMethods.moss_free_index_info_list(outPtr, count);
            }
        }
    }

    public bool DeleteIndex(string name)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_delete_index(_handle, arena.String(name), out bool deleted));
            return deleted;
        }
    }

    public JobStatusResponse GetJobStatus(string jobId)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_get_job_status(_handle, arena.String(jobId), out IntPtr outPtr));
            try
            {
                var n = Marshal.PtrToStructure<MossJobStatusResponse>(outPtr);
                return new JobStatusResponse
                {
                    JobId = Utf8.Read(n.job_id),
                    Status = Utf8.Read(n.status),
                    Progress = n.progress,
                    CurrentPhase = Utf8.ReadOptional(n.current_phase),
                    Error = Utf8.ReadOptional(n.error),
                    CreatedAt = Utf8.Read(n.created_at),
                    UpdatedAt = Utf8.Read(n.updated_at),
                    CompletedAt = Utf8.ReadOptional(n.completed_at),
                };
            }
            finally
            {
                NativeMethods.moss_free_job_status_response(outPtr);
            }
        }
    }

    // ---- Local runtime ---------------------------------------------------

    public IndexInfo LoadIndex(string name, LoadIndexOptions? options)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            IntPtr optsPtr = IntPtr.Zero;
            if (options is not null)
            {
                var native = new MossLoadIndexOptions
                {
                    auto_refresh = options.AutoRefresh,
                    polling_interval_secs = options.PollingIntervalInSeconds,
                };
                optsPtr = arena.StructArray(new[] { native });
            }
            Check(NativeMethods.moss_client_load_index(_handle, arena.String(name), optsPtr, out IntPtr outPtr));
            try
            {
                return ReadIndexInfo(Marshal.PtrToStructure<MossIndexInfo>(outPtr));
            }
            finally
            {
                NativeMethods.moss_free_index_info(outPtr);
            }
        }
    }

    public void UnloadIndex(string name)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_unload_index(_handle, arena.String(name)));
        }
    }

    public RefreshResult RefreshIndex(string name)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            Check(NativeMethods.moss_client_refresh_index(_handle, arena.String(name), out IntPtr outPtr));
            try
            {
                var n = Marshal.PtrToStructure<MossRefreshResult>(outPtr);
                return new RefreshResult
                {
                    IndexName = Utf8.Read(n.index_name),
                    PreviousUpdatedAt = Utf8.Read(n.previous_updated_at),
                    NewUpdatedAt = Utf8.Read(n.new_updated_at),
                    WasUpdated = n.was_updated,
                };
            }
            finally
            {
                NativeMethods.moss_free_refresh_result(outPtr);
            }
        }
    }

    public SearchResult Query(string name, string query, QueryOptions options)
    {
        lock (_gate)
        {
            EnsureOpen();
            using var arena = new NativeArena();
            var native = new MossQueryOptions
            {
                top_k = (nuint)Math.Max(0, options.TopK),
                alpha = options.Alpha,
                filter_json = arena.String(options.FilterJson),
                embedding = arena.FloatArray(options.Embedding),
                embedding_dim = (nuint)(options.Embedding?.Count ?? 0),
            };
            IntPtr optsPtr = arena.StructArray(new[] { native });
            Check(NativeMethods.moss_client_query(
                _handle, arena.String(name), arena.String(query), optsPtr, out IntPtr outPtr));
            try
            {
                return ReadSearchResult(outPtr);
            }
            finally
            {
                NativeMethods.moss_free_search_result(outPtr);
            }
        }
    }

    // ---- Input marshaling ------------------------------------------------

    private static IntPtr BuildDocuments(NativeArena arena, IReadOnlyList<DocumentInfo> docs)
    {
        if (docs.Count == 0) return IntPtr.Zero;
        var natives = new MossDocumentInfo[docs.Count];
        for (int i = 0; i < docs.Count; i++)
        {
            DocumentInfo doc = docs[i];
            IntPtr metaPtr = IntPtr.Zero;
            int metaCount = 0;
            if (doc.Metadata is { Count: > 0 })
            {
                var entries = new List<MossMetadataEntry>(doc.Metadata.Count);
                foreach (KeyValuePair<string, string> kv in doc.Metadata)
                    entries.Add(new MossMetadataEntry { key = arena.String(kv.Key), value = arena.String(kv.Value) });
                metaPtr = arena.StructArray(entries);
                metaCount = entries.Count;
            }
            natives[i] = new MossDocumentInfo
            {
                id = arena.String(doc.Id),
                text = arena.String(doc.Text),
                metadata = metaPtr,
                metadata_count = (nuint)metaCount,
                embedding = arena.FloatArray(doc.Embedding),
                embedding_dim = (nuint)(doc.Embedding?.Count ?? 0),
            };
        }
        return arena.StructArray(natives);
    }

    // ---- Output marshaling -----------------------------------------------

    private static MutationResult ReadMutationResult(IntPtr ptr)
    {
        try
        {
            var n = Marshal.PtrToStructure<MossMutationResult>(ptr);
            return new MutationResult
            {
                JobId = Utf8.Read(n.job_id),
                IndexName = Utf8.Read(n.index_name),
                DocCount = (int)n.doc_count,
            };
        }
        finally
        {
            NativeMethods.moss_free_mutation_result(ptr);
        }
    }

    private static IndexInfo ReadIndexInfo(MossIndexInfo n) => new()
    {
        Id = Utf8.Read(n.id),
        Name = Utf8.Read(n.name),
        Version = Utf8.ReadOptional(n.version),
        Status = Utf8.Read(n.status),
        DocCount = (int)n.doc_count,
        CreatedAt = Utf8.ReadOptional(n.created_at),
        UpdatedAt = Utf8.ReadOptional(n.updated_at),
        Model = new ModelRef { Id = Utf8.Read(n.model.id), Version = Utf8.ReadOptional(n.model.version) },
    };

    private static IReadOnlyList<DocumentInfo> ReadDocuments(IntPtr ptr, nuint count)
    {
        if (ptr == IntPtr.Zero || count == 0) return Array.Empty<DocumentInfo>();
        int size = Marshal.SizeOf<MossDocumentInfo>();
        var result = new List<DocumentInfo>((int)count);
        for (nuint i = 0; i < count; i++)
        {
            var n = Marshal.PtrToStructure<MossDocumentInfo>(ptr + (int)i * size);
            result.Add(new DocumentInfo
            {
                Id = Utf8.Read(n.id),
                Text = Utf8.Read(n.text),
                Metadata = ReadMetadata(n.metadata, n.metadata_count),
                Embedding = ReadFloats(n.embedding, n.embedding_dim),
            });
        }
        return result;
    }

    private static SearchResult ReadSearchResult(IntPtr ptr)
    {
        var n = Marshal.PtrToStructure<MossSearchResult>(ptr);
        var docs = new List<ScoredDocument>((int)n.doc_count);
        if (n.docs != IntPtr.Zero && n.doc_count > 0)
        {
            int size = Marshal.SizeOf<MossSearchResultDoc>();
            for (nuint i = 0; i < n.doc_count; i++)
            {
                var d = Marshal.PtrToStructure<MossSearchResultDoc>(n.docs + (int)i * size);
                docs.Add(new ScoredDocument
                {
                    Id = Utf8.Read(d.id),
                    Text = Utf8.Read(d.text),
                    Metadata = ReadMetadata(d.metadata, d.metadata_count),
                    Score = d.score,
                });
            }
        }
        return new SearchResult
        {
            Docs = docs,
            Query = Utf8.Read(n.query),
            IndexName = Utf8.ReadOptional(n.index_name),
            TimeTakenMs = (int)n.time_taken_ms,
        };
    }

    private static IReadOnlyDictionary<string, string>? ReadMetadata(IntPtr entries, nuint count)
    {
        if (entries == IntPtr.Zero || count == 0) return null;
        int size = Marshal.SizeOf<MossMetadataEntry>();
        var map = new Dictionary<string, string>((int)count);
        for (nuint i = 0; i < count; i++)
        {
            var e = Marshal.PtrToStructure<MossMetadataEntry>(entries + (int)i * size);
            map[Utf8.Read(e.key)] = Utf8.Read(e.value);
        }
        return map;
    }

    private static IReadOnlyList<float>? ReadFloats(IntPtr ptr, nuint count)
    {
        if (ptr == IntPtr.Zero || count == 0) return null;
        var values = new float[(int)count];
        Marshal.Copy(ptr, values, 0, (int)count);
        return values;
    }

    // ---- Lifetime + errors ----------------------------------------------

    private void EnsureOpen()
    {
        if (_handle.IsInvalid || _handle.IsClosed)
            throw new ObjectDisposedException(nameof(MossClient));
    }

    private static void Check(MossResult result)
    {
        if (result == MossResult.Ok) return;
        IntPtr msgPtr = NativeMethods.moss_last_error();
        string message = msgPtr == IntPtr.Zero ? "libmoss call failed" : Utf8.Read(msgPtr);
        throw new MossException((int)result, message);
    }

    public void Dispose()
    {
        lock (_gate)
        {
            _handle.Dispose();
        }
    }
}
