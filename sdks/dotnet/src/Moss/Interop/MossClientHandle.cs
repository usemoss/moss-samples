using System;
using System.Runtime.InteropServices;

namespace Moss.Interop;

/// <summary>
/// Owns the native <c>MossClient*</c>. Deriving from <see cref="SafeHandle"/>
/// means the handle is reference-counted during P/Invoke calls and freed via
/// <c>moss_client_free</c> from <see cref="ReleaseHandle"/> — including during
/// finalization, so a leaked (undisposed) client still releases native state.
/// </summary>
internal sealed class MossClientHandle : SafeHandle
{
    public MossClientHandle() : base(IntPtr.Zero, ownsHandle: true) { }

    public override bool IsInvalid => handle == IntPtr.Zero;

    /// <summary>Adopt a raw handle produced by <c>moss_client_new</c>.</summary>
    internal void SetRawHandle(IntPtr raw) => SetHandle(raw);

    protected override bool ReleaseHandle()
    {
        NativeMethods.moss_client_free(handle);
        return true;
    }
}
