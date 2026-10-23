using System;

namespace Moss;

/// <summary>
/// Thrown when a call into the native <c>libmoss</c> runtime fails.
/// <see cref="Code"/> carries the raw <c>MossResult</c> status code and
/// <see cref="Exception.Message"/> the human-readable message from
/// <c>moss_last_error</c>.
/// </summary>
public sealed class MossException : Exception
{
    /// <summary>The raw <c>MossResult</c> status code returned by the native call.</summary>
    public int Code { get; }

    public MossException(int code, string message) : base(message)
    {
        Code = code;
    }
}
