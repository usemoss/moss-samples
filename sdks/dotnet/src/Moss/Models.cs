using System.Collections.Generic;

namespace Moss;

/// <summary>A document to index or a document returned from the store.</summary>
public sealed class DocumentInfo
{
    /// <summary>Stable, caller-supplied identifier for the document.</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>The document text that gets embedded and searched.</summary>
    public string Text { get; set; } = string.Empty;

    /// <summary>Optional string-to-string metadata used for filtering.</summary>
    public IReadOnlyDictionary<string, string>? Metadata { get; set; }

    /// <summary>Optional precomputed embedding. When null, Moss embeds the text.</summary>
    public IReadOnlyList<float>? Embedding { get; set; }

    public DocumentInfo() { }

    public DocumentInfo(string id, string text,
        IReadOnlyDictionary<string, string>? metadata = null,
        IReadOnlyList<float>? embedding = null)
    {
        Id = id;
        Text = text;
        Metadata = metadata;
        Embedding = embedding;
    }
}

/// <summary>Options controlling how documents are written.</summary>
public sealed class MutationOptions
{
    /// <summary>When true, existing documents with the same id are overwritten.</summary>
    public bool? Upsert { get; set; }
}

/// <summary>Result of a create/add/delete documents operation.</summary>
public sealed class MutationResult
{
    public string JobId { get; init; } = string.Empty;
    public string IndexName { get; init; } = string.Empty;
    public int DocCount { get; init; }
}

/// <summary>Reference to the embedding model backing an index.</summary>
public sealed class ModelRef
{
    public string Id { get; init; } = string.Empty;
    public string? Version { get; init; }
}

/// <summary>Metadata describing an index.</summary>
public sealed class IndexInfo
{
    public string Id { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public string? Version { get; init; }
    public string Status { get; init; } = string.Empty;
    public int DocCount { get; init; }
    public string? CreatedAt { get; init; }
    public string? UpdatedAt { get; init; }
    public ModelRef Model { get; init; } = new();
}

/// <summary>Status of an asynchronous indexing job.</summary>
public sealed class JobStatusResponse
{
    public string JobId { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;
    public double Progress { get; init; }
    public string? CurrentPhase { get; init; }
    public string? Error { get; init; }
    public string CreatedAt { get; init; } = string.Empty;
    public string UpdatedAt { get; init; } = string.Empty;
    public string? CompletedAt { get; init; }
}

/// <summary>Options for loading an index into the local runtime.</summary>
public sealed class LoadIndexOptions
{
    /// <summary>Poll the cloud for updates and hot-reload the local copy.</summary>
    public bool AutoRefresh { get; set; }

    /// <summary>Interval between refresh polls, in seconds.</summary>
    public ulong PollingIntervalInSeconds { get; set; }
}

/// <summary>Options controlling a query.</summary>
public sealed class QueryOptions
{
    /// <summary>Maximum number of results to return.</summary>
    public int TopK { get; set; } = 10;

    /// <summary>
    /// Hybrid weighting between lexical and semantic scores, in [0, 1].
    /// 0 = lexical only, 1 = semantic only.
    /// </summary>
    public float Alpha { get; set; } = 0.5f;

    /// <summary>Optional metadata filter, expressed as a JSON string.</summary>
    public string? FilterJson { get; set; }

    /// <summary>Optional precomputed query embedding. When null, Moss embeds the query text.</summary>
    public IReadOnlyList<float>? Embedding { get; set; }
}

/// <summary>A single scored document returned by a query.</summary>
public sealed class ScoredDocument
{
    public string Id { get; init; } = string.Empty;
    public string Text { get; init; } = string.Empty;
    public IReadOnlyDictionary<string, string>? Metadata { get; init; }
    public double Score { get; init; }
}

/// <summary>Result of a query.</summary>
public sealed class SearchResult
{
    public IReadOnlyList<ScoredDocument> Docs { get; init; } = System.Array.Empty<ScoredDocument>();
    public string Query { get; init; } = string.Empty;
    public string? IndexName { get; init; }
    public int TimeTakenMs { get; init; }
}

/// <summary>Result of refreshing a locally loaded index.</summary>
public sealed class RefreshResult
{
    public string IndexName { get; init; } = string.Empty;
    public string PreviousUpdatedAt { get; init; } = string.Empty;
    public string NewUpdatedAt { get; init; } = string.Empty;
    public bool WasUpdated { get; init; }
}
