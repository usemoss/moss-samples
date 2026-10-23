using System;
using System.Collections.Generic;
using Moss;
using Xunit;

namespace Moss.Tests;

/// <summary>
/// Verifies that inputs are defensively copied, so a caller mutating their own
/// collections after an async call cannot change what gets sent to native code.
/// </summary>
public class SnapshotTests
{
    [Fact]
    public void SnapshotDoc_DeepCopiesMetadataAndEmbedding()
    {
        var meta = new Dictionary<string, string> { ["k"] = "v" };
        var embedding = new List<float> { 1f, 2f };
        var doc = new DocumentInfo("1", "text", meta, embedding);

        DocumentInfo snap = MossClient.SnapshotDoc(doc);

        // Mutate the caller's originals after snapshotting.
        meta["k"] = "changed";
        embedding[0] = 9f;

        Assert.Equal("v", snap.Metadata!["k"]);
        Assert.Equal(1f, snap.Embedding![0]);
        Assert.NotSame(doc.Metadata, snap.Metadata);
        Assert.NotSame(doc.Embedding, snap.Embedding);
    }

    [Fact]
    public void SnapshotDoc_PreservesNullMetadataAndEmbedding()
    {
        DocumentInfo snap = MossClient.SnapshotDoc(new DocumentInfo("1", "text"));
        Assert.Null(snap.Metadata);
        Assert.Null(snap.Embedding);
    }

    [Fact]
    public void SnapshotQuery_CopiesEmbeddingAndScalars()
    {
        var embedding = new List<float> { 0.5f };
        var opts = new QueryOptions { TopK = 3, Alpha = 0.2f, FilterJson = "{}", Embedding = embedding };

        QueryOptions snap = MossClient.SnapshotQuery(opts);
        embedding[0] = 9f;

        Assert.Equal(3, snap.TopK);
        Assert.Equal(0.2f, snap.Alpha);
        Assert.Equal("{}", snap.FilterJson);
        Assert.Equal(0.5f, snap.Embedding![0]);
    }

    [Fact]
    public void SnapshotDoc_ThrowsOnNullId()
    {
        Assert.Throws<ArgumentException>(() => MossClient.SnapshotDoc(new DocumentInfo(null!, "text")));
    }

    [Fact]
    public void SnapshotDoc_ThrowsOnNullText()
    {
        Assert.Throws<ArgumentException>(() => MossClient.SnapshotDoc(new DocumentInfo("1", null!)));
    }

    [Fact]
    public void SnapshotDoc_ThrowsOnNullMetadataValue()
    {
        var meta = new Dictionary<string, string> { ["k"] = null! };
        Assert.Throws<ArgumentException>(() => MossClient.SnapshotDoc(new DocumentInfo("1", "text", meta)));
    }

    [Fact]
    public void SnapshotIds_ThrowsOnNullEntry()
    {
        Assert.Throws<ArgumentException>(() => MossClient.SnapshotIds(new[] { "a", null! }));
    }
}
