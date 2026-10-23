using System;
using Moss;
using Xunit;

namespace Moss.Tests;

/// <summary>
/// Credential validation happens before any native call, so these run without
/// libmoss present.
/// </summary>
public class ClientValidationTests
{
    [Theory]
    [InlineData("")]
    [InlineData(null)]
    public void Constructor_RejectsMissingProjectId(string? projectId)
    {
        Assert.Throws<ArgumentException>(() => new MossClient(projectId!, "key"));
    }

    [Theory]
    [InlineData("")]
    [InlineData(null)]
    public void Constructor_RejectsMissingProjectKey(string? projectKey)
    {
        Assert.Throws<ArgumentException>(() => new MossClient("project", projectKey!));
    }
}
