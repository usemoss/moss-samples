using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moss.Interop;

namespace Moss;

/// <summary>
/// Client for Moss — fast on-device retrieval. Wraps the native <c>libmoss</c>
/// runtime and exposes an async API for index management, hybrid search, and
/// metadata filtering.
/// </summary>
/// <remarks>
/// The client owns native resources; dispose it when finished. Native calls are
/// blocking and are marshaled onto the thread pool. Operations are serialized
/// through a cancellable gate, so a single client may be shared across tasks.
/// Inputs are snapshotted before work is queued, so callers may safely mutate
/// their own collections after an async method returns.
/// </remarks>
public sealed class MossClient : IDisposable
{
    private readonly NativeClient _native;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private int _disposed;

    /// <summary>Create a client for the given Moss project credentials.</summary>
    /// <exception cref="ArgumentException">A credential is null or empty.</exception>
    /// <exception cref="MossException">The native runtime failed to initialize.</exception>
    public MossClient(string projectId, string projectKey)
    {
        if (string.IsNullOrEmpty(projectId)) throw new ArgumentException("projectId is required", nameof(projectId));
        if (string.IsNullOrEmpty(projectKey)) throw new ArgumentException("projectKey is required", nameof(projectKey));
        _native = new NativeClient(projectId, projectKey);
    }

    // ---- Management ------------------------------------------------------

    /// <summary>Create a new index and enqueue the supplied documents for indexing.</summary>
    public Task<MutationResult> CreateIndexAsync(
        string name, IEnumerable<DocumentInfo> docs, string? modelId = null, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        DocumentInfo[] snapshot = SnapshotDocs(docs);
        return RunAsync(() => _native.CreateIndex(name, snapshot, modelId), cancellationToken);
    }

    /// <summary>Add (or upsert) documents to an existing index.</summary>
    public Task<MutationResult> AddDocsAsync(
        string name, IEnumerable<DocumentInfo> docs, MutationOptions? options = null, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        DocumentInfo[] snapshot = SnapshotDocs(docs);
        MutationOptions? optionsCopy = options is null ? null : new MutationOptions { Upsert = options.Upsert };
        return RunAsync(() => _native.AddDocs(name, snapshot, optionsCopy), cancellationToken);
    }

    /// <summary>Delete documents from an index by id.</summary>
    public Task<MutationResult> DeleteDocsAsync(
        string name, IEnumerable<string> docIds, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        string[] snapshot = SnapshotIds(docIds);
        return RunAsync(() => _native.DeleteDocs(name, snapshot), cancellationToken);
    }

    /// <summary>Fetch documents from an index by id.</summary>
    public Task<IReadOnlyList<DocumentInfo>> GetDocsAsync(
        string name, IEnumerable<string> docIds, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        string[] snapshot = SnapshotIds(docIds);
        return RunAsync(() => _native.GetDocs(name, snapshot), cancellationToken);
    }

    /// <summary>Get metadata for a single index.</summary>
    public Task<IndexInfo> GetIndexAsync(string name, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        return RunAsync(() => _native.GetIndex(name), cancellationToken);
    }

    /// <summary>List all indexes in the project.</summary>
    public Task<IReadOnlyList<IndexInfo>> ListIndexesAsync(CancellationToken cancellationToken = default)
        => RunAsync(() => _native.ListIndexes(), cancellationToken);

    /// <summary>Delete an index. Returns true if an index was removed.</summary>
    public Task<bool> DeleteIndexAsync(string name, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        return RunAsync(() => _native.DeleteIndex(name), cancellationToken);
    }

    /// <summary>Poll the status of an asynchronous indexing job.</summary>
    public Task<JobStatusResponse> GetJobStatusAsync(string jobId, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrEmpty(jobId)) throw new ArgumentException("jobId is required", nameof(jobId));
        return RunAsync(() => _native.GetJobStatus(jobId), cancellationToken);
    }

    // ---- Local runtime ---------------------------------------------------

    /// <summary>Load an index into the local runtime so it can be queried on-device.</summary>
    public Task<IndexInfo> LoadIndexAsync(
        string name, LoadIndexOptions? options = null, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        LoadIndexOptions? optionsCopy = options is null
            ? null
            : new LoadIndexOptions { AutoRefresh = options.AutoRefresh, PollingIntervalInSeconds = options.PollingIntervalInSeconds };
        return RunAsync(() => _native.LoadIndex(name, optionsCopy), cancellationToken);
    }

    /// <summary>Unload a previously loaded index from the local runtime.</summary>
    public Task UnloadIndexAsync(string name, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        return RunAsync(() => { _native.UnloadIndex(name); return true; }, cancellationToken);
    }

    /// <summary>Refresh a locally loaded index against the latest cloud state.</summary>
    public Task<RefreshResult> RefreshIndexAsync(string name, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        return RunAsync(() => _native.RefreshIndex(name), cancellationToken);
    }

    /// <summary>Run a hybrid (lexical + semantic) query against a loaded index.</summary>
    public Task<SearchResult> QueryAsync(
        string name, string query, QueryOptions? options = null, CancellationToken cancellationToken = default)
    {
        RequireName(name);
        if (query is null) throw new ArgumentNullException(nameof(query));
        QueryOptions snapshot = SnapshotQuery(options ?? new QueryOptions());
        return RunAsync(() => _native.Query(name, query, snapshot), cancellationToken);
    }

    // ---- Serialization + cancellation ------------------------------------

    private async Task<T> RunAsync<T>(Func<T> action, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        // WaitAsync honors cancellation while the operation is still queued, so a
        // cancelled call never reaches the native layer.
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            return await Task.Run(action, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    // ---- Input snapshots -------------------------------------------------

    private static DocumentInfo[] SnapshotDocs(IEnumerable<DocumentInfo> docs)
    {
        if (docs is null) throw new ArgumentNullException(nameof(docs));
        return docs.Select(SnapshotDoc).ToArray();
    }

    internal static DocumentInfo SnapshotDoc(DocumentInfo doc)
    {
        if (doc is null) throw new ArgumentNullException(nameof(doc));
        // Required C-ABI strings must never be marshaled as NULL. Nullable
        // annotations don't protect against nullable-disabled callers,
        // deserialization, or `null!`, so validate explicitly.
        if (doc.Id is null) throw new ArgumentException("DocumentInfo.Id must not be null", nameof(doc));
        if (doc.Text is null) throw new ArgumentException("DocumentInfo.Text must not be null", nameof(doc));

        IReadOnlyDictionary<string, string>? metadata = null;
        if (doc.Metadata is not null)
        {
            var copy = new Dictionary<string, string>(doc.Metadata.Count);
            foreach (KeyValuePair<string, string> kv in doc.Metadata)
            {
                if (kv.Key is null) throw new ArgumentException("DocumentInfo.Metadata keys must not be null", nameof(doc));
                if (kv.Value is null) throw new ArgumentException("DocumentInfo.Metadata values must not be null", nameof(doc));
                copy[kv.Key] = kv.Value;
            }
            metadata = copy;
        }

        IReadOnlyList<float>? embedding = doc.Embedding?.ToArray();
        return new DocumentInfo(doc.Id, doc.Text, metadata, embedding);
    }

    internal static string[] SnapshotIds(IEnumerable<string> docIds)
    {
        if (docIds is null) throw new ArgumentNullException(nameof(docIds));
        string[] array = docIds.ToArray();
        foreach (string id in array)
            if (id is null) throw new ArgumentException("document ids must not be null", nameof(docIds));
        return array;
    }

    internal static QueryOptions SnapshotQuery(QueryOptions options) => new()
    {
        TopK = options.TopK,
        Alpha = options.Alpha,
        FilterJson = options.FilterJson,
        Embedding = options.Embedding?.ToArray(),
    };

    // ---- Helpers ---------------------------------------------------------

    private static void RequireName(string name)
    {
        if (string.IsNullOrEmpty(name)) throw new ArgumentException("index name is required", nameof(name));
    }

    private void ThrowIfDisposed()
    {
        if (Volatile.Read(ref _disposed) != 0) throw new ObjectDisposedException(nameof(MossClient));
    }

    /// <summary>Release the native client and its resources.</summary>
    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
        _native.Dispose();
        // Intentionally not disposing _gate: an in-flight RunAsync still owns it
        // and releases it in its finally block, so disposing here would race and
        // surface a spurious ObjectDisposedException from Release(). SemaphoreSlim
        // holds no unmanaged resource unless its AvailableWaitHandle is
        // materialized, which this type never does.
    }
}
