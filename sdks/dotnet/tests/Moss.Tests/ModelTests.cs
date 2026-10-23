using System.Collections.Generic;
using Moss;
using Xunit;

namespace Moss.Tests;

public class ModelTests
{
    [Fact]
    public void QueryOptions_HasSensibleDefaults()
    {
        var opts = new QueryOptions();
        Assert.Equal(10, opts.TopK);
        Assert.Equal(0.5f, opts.Alpha);
        Assert.Null(opts.FilterJson);
        Assert.Null(opts.Embedding);
    }

    [Fact]
    public void DocumentInfo_ConstructorSetsFields()
    {
        var meta = new Dictionary<string, string> { ["lang"] = "en" };
        var embedding = new[] { 0.1f, 0.2f };
        var doc = new DocumentInfo("doc-1", "hello world", meta, embedding);

        Assert.Equal("doc-1", doc.Id);
        Assert.Equal("hello world", doc.Text);
        Assert.Same(meta, doc.Metadata);
        Assert.Same(embedding, doc.Embedding);
    }

    [Fact]
    public void DocumentInfo_DefaultsAreEmptyNotNull()
    {
        var doc = new DocumentInfo();
        Assert.Equal(string.Empty, doc.Id);
        Assert.Equal(string.Empty, doc.Text);
        Assert.Null(doc.Metadata);
        Assert.Null(doc.Embedding);
    }

    [Fact]
    public void SearchResult_DefaultsToEmptyDocs()
    {
        var result = new SearchResult();
        Assert.NotNull(result.Docs);
        Assert.Empty(result.Docs);
    }
}
