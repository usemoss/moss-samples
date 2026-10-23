using System;
using System.Runtime.InteropServices;

namespace Moss.Interop;

// These structs mirror the C ABI declared in libmoss.h (the same surface the
// Go bindings bind via cgo). Field order, types, and layout must match exactly.
// char*  -> IntPtr (NUL-terminated UTF-8)
// uintptr_t / size_t -> nuint
// bool   -> [MarshalAs(I1)] bool
// float  -> float, double -> double, uint64_t -> ulong

/// <summary>Status code returned by every native call. 0 == success.</summary>
internal enum MossResult
{
    Ok = 0,
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossMetadataEntry
{
    public IntPtr key;
    public IntPtr value;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossDocumentInfo
{
    public IntPtr id;
    public IntPtr text;
    public IntPtr metadata;        // MossMetadataEntry*
    public nuint metadata_count;
    public IntPtr embedding;       // float*
    public nuint embedding_dim;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossMutationOptions
{
    [MarshalAs(UnmanagedType.I1)] public bool upsert;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossMutationResult
{
    public IntPtr job_id;
    public IntPtr index_name;
    public nuint doc_count;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossModelRef
{
    public IntPtr id;
    public IntPtr version;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossIndexInfo
{
    public IntPtr id;
    public IntPtr name;
    public IntPtr version;
    public IntPtr status;
    public nuint doc_count;
    public IntPtr created_at;
    public IntPtr updated_at;
    public MossModelRef model;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossJobStatusResponse
{
    public IntPtr job_id;
    public IntPtr status;
    public double progress;
    public IntPtr current_phase;
    public IntPtr error;
    public IntPtr created_at;
    public IntPtr updated_at;
    public IntPtr completed_at;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossLoadIndexOptions
{
    [MarshalAs(UnmanagedType.I1)] public bool auto_refresh;
    public ulong polling_interval_secs;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossQueryOptions
{
    public nuint top_k;
    public float alpha;
    public IntPtr filter_json;     // char*
    public IntPtr embedding;       // float*
    public nuint embedding_dim;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossSearchResultDoc
{
    public IntPtr id;
    public IntPtr text;
    public IntPtr metadata;        // MossMetadataEntry*
    public nuint metadata_count;
    public double score;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossSearchResult
{
    public IntPtr docs;            // MossSearchResultDoc*
    public nuint doc_count;
    public IntPtr query;
    public IntPtr index_name;
    public nuint time_taken_ms;
}

[StructLayout(LayoutKind.Sequential)]
internal struct MossRefreshResult
{
    public IntPtr index_name;
    public IntPtr previous_updated_at;
    public IntPtr new_updated_at;
    [MarshalAs(UnmanagedType.I1)] public bool was_updated;
}
