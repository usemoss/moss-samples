using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Moss.Interop;
using Xunit;

namespace Moss.Tests;

/// <summary>
/// Exercises the marshaling helpers and native struct layouts. None of these
/// call into libmoss, so they run anywhere.
/// </summary>
public class InteropTests
{
    [Theory]
    [InlineData("hello")]
    [InlineData("")]
    [InlineData("café über 日本語 🚀")]
    public void Utf8_RoundTrips(string value)
    {
        IntPtr p = Utf8.Alloc(value);
        try
        {
            Assert.Equal(value, Utf8.Read(p));
        }
        finally
        {
            Marshal.FreeCoTaskMem(p);
        }
    }

    [Fact]
    public void Utf8_NullPointerReadsAsEmptyOrNull()
    {
        Assert.Equal(string.Empty, Utf8.Read(IntPtr.Zero));
        Assert.Null(Utf8.ReadOptional(IntPtr.Zero));
    }

    [Fact]
    public void Utf8_AllocNullReturnsZero()
    {
        Assert.Equal(IntPtr.Zero, Utf8.Alloc(null));
    }

    [Fact]
    public void NativeArena_FloatArrayRoundTrips()
    {
        var values = new[] { 1.5f, -2.25f, 3.0f };
        using var arena = new NativeArena();
        IntPtr p = arena.FloatArray(values);
        Assert.NotEqual(IntPtr.Zero, p);

        var read = new float[values.Length];
        Marshal.Copy(p, read, 0, values.Length);
        Assert.Equal(values, read);
    }

    [Fact]
    public void NativeArena_EmptyCollectionsReturnZero()
    {
        using var arena = new NativeArena();
        Assert.Equal(IntPtr.Zero, arena.FloatArray(Array.Empty<float>()));
        Assert.Equal(IntPtr.Zero, arena.StringArray(Array.Empty<string>()));
        Assert.Equal(IntPtr.Zero, arena.FloatArray(null));
    }

    [Fact]
    public void NativeArena_StringArrayWritesReadablePointers()
    {
        var values = new[] { "alpha", "beta" };
        using var arena = new NativeArena();
        IntPtr block = arena.StringArray(values);
        Assert.NotEqual(IntPtr.Zero, block);

        for (int i = 0; i < values.Length; i++)
        {
            IntPtr strPtr = Marshal.ReadIntPtr(block, i * IntPtr.Size);
            Assert.Equal(values[i], Utf8.Read(strPtr));
        }
    }

    [Fact]
    public void NativeArena_DisposeIsIdempotent()
    {
        var arena = new NativeArena();
        arena.String("x");
        arena.Dispose();
        arena.Dispose(); // must not throw
    }

    // Layout sanity: sizes are pointer-derived, so these catch accidental field
    // reordering or type changes in the ABI mirror structs.
    [Fact]
    public void NativeStructs_HaveExpectedSizes()
    {
        Assert.Equal(2 * IntPtr.Size, Marshal.SizeOf<MossMetadataEntry>());
        Assert.Equal(2 * IntPtr.Size, Marshal.SizeOf<MossModelRef>());
        // 4 pointers + 2 nuint
        Assert.Equal(6 * IntPtr.Size, Marshal.SizeOf<MossDocumentInfo>());
    }
}
