using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Moss.Interop;

/// <summary>UTF-8 string marshaling helpers for the native boundary.</summary>
internal static class Utf8
{
    /// <summary>Allocates a NUL-terminated UTF-8 copy of <paramref name="value"/>, or
    /// <see cref="IntPtr.Zero"/> when it is null. Free with <see cref="Marshal.FreeCoTaskMem"/>.</summary>
    public static IntPtr Alloc(string? value)
        => value is null ? IntPtr.Zero : Marshal.StringToCoTaskMemUTF8(value);

    /// <summary>Reads a NUL-terminated UTF-8 string, mapping a null pointer to "".</summary>
    public static string Read(IntPtr ptr)
        => ptr == IntPtr.Zero ? string.Empty : Marshal.PtrToStringUTF8(ptr) ?? string.Empty;

    /// <summary>Reads a NUL-terminated UTF-8 string, preserving null as null (for optional fields).</summary>
    public static string? ReadOptional(IntPtr ptr)
        => ptr == IntPtr.Zero ? null : Marshal.PtrToStringUTF8(ptr);
}

/// <summary>
/// Tracks native allocations made while marshaling inputs and frees them all on
/// <see cref="Dispose"/>. Strings are allocated via CoTaskMem; raw blocks via HGlobal.
/// </summary>
internal sealed class NativeArena : IDisposable
{
    private readonly List<IntPtr> _coTaskMem = new();
    private readonly List<IntPtr> _hGlobal = new();

    /// <summary>Allocate a UTF-8 string tracked by this arena.</summary>
    public IntPtr String(string? value)
    {
        IntPtr p = Utf8.Alloc(value);
        if (p != IntPtr.Zero) _coTaskMem.Add(p);
        return p;
    }

    /// <summary>Allocate a raw block of <paramref name="bytes"/> bytes tracked by this arena.</summary>
    public IntPtr Alloc(int bytes)
    {
        IntPtr p = Marshal.AllocHGlobal(bytes);
        _hGlobal.Add(p);
        return p;
    }

    /// <summary>Marshal an array of contiguous structs into a tracked native block.</summary>
    public IntPtr StructArray<T>(IReadOnlyList<T> items) where T : struct
    {
        if (items.Count == 0) return IntPtr.Zero;
        int size = Marshal.SizeOf<T>();
        IntPtr block = Alloc(size * items.Count);
        for (int i = 0; i < items.Count; i++)
            Marshal.StructureToPtr(items[i], block + i * size, false);
        return block;
    }

    /// <summary>Marshal an array of floats into a tracked native block.</summary>
    public IntPtr FloatArray(IReadOnlyList<float>? values)
    {
        if (values is null || values.Count == 0) return IntPtr.Zero;
        IntPtr block = Alloc(sizeof(float) * values.Count);
        var tmp = new float[values.Count];
        for (int i = 0; i < values.Count; i++) tmp[i] = values[i];
        Marshal.Copy(tmp, 0, block, tmp.Length);
        return block;
    }

    /// <summary>Marshal an array of UTF-8 strings into a tracked native array of char*.</summary>
    public IntPtr StringArray(IReadOnlyList<string> values)
    {
        if (values.Count == 0) return IntPtr.Zero;
        IntPtr block = Alloc(IntPtr.Size * values.Count);
        for (int i = 0; i < values.Count; i++)
            Marshal.WriteIntPtr(block, i * IntPtr.Size, String(values[i]));
        return block;
    }

    public void Dispose()
    {
        foreach (IntPtr p in _coTaskMem) Marshal.FreeCoTaskMem(p);
        foreach (IntPtr p in _hGlobal) Marshal.FreeHGlobal(p);
        _coTaskMem.Clear();
        _hGlobal.Clear();
    }
}
