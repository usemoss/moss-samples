import ExpoModulesCore
import Foundation
import MossC
import UIKit

/**
 * SharedObject wrapping a native MossClient handle.
 * Methods return dictionaries / arrays that map cleanly across the JSI bridge.
 */
/// Holds the closure that forwards a native auth-token request to JS.
///
/// A pointer to this box is handed to the native side as `user_data` and must
/// stay valid for the whole life of the client, so it is retained manually and
/// released only after `moss_client_free`.
final class AuthBridgeBox {
  let emit: (UInt32) -> Void
  init(emit: @escaping (UInt32) -> Void) { self.emit = emit }
}

/// C trampoline registered as `MossAuthNotifyFn`.
///
/// The native runtime calls this from an arbitrary Rust thread, possibly
/// concurrently, whenever it needs a bearer token. It must not block: it only
/// forwards the request id to JS, which answers later via
/// `moss_resolve_auth_request` / `moss_reject_auth_request`.
@_cdecl("_moss_rn_auth_notify")
func mossRNAuthNotify(requestId: UInt32, userData: UnsafeMutableRawPointer?) {
  guard let userData else { return }
  let box = Unmanaged<AuthBridgeBox>.fromOpaque(userData).takeUnretainedValue()
  box.emit(requestId)
}

public final class MossClientSharedObject: SharedObject {
  private var handle: OpaquePointer?
  private var closed = false
  private var inFlight = 0
  /// Retained `AuthBridgeBox` pointer for authenticator-backed clients, or nil
  /// for project-key clients. Released exactly once, after the handle is freed.
  private var authUserData: UnsafeMutableRawPointer?
  /// Guards `handle` / `closed` / `inFlight`.
  ///
  /// The operations are `AsyncFunction`s that run off the JS thread while
  /// `close()` is a synchronous `Function` on it, so freeing the handle
  /// eagerly would be a use-after-free. Ownership of the free is therefore
  /// handed to whoever is last out — see `close()` and `release()`.
  private let state = NSLock()

  public init(projectId: String, projectKey: String) throws {
    try Self.ensureModelCacheDir()
    let deviceId = Self.stableDeviceId()
    var raw: OpaquePointer?
    let status = projectId.withCString { pid in
      projectKey.withCString { pkey in
        deviceId.withCString { did in
          moss_client_new_with_device_id(pid, pkey, did, &raw)
        }
      }
    }
    try Self.throwIfErr(status)
    guard let raw else {
      throw Self.mossError(code: -7)
    }
    self.handle = raw
    self.authUserData = nil
    super.init()
  }

  /// Construct a client that asks the host for a short-lived bearer token
  /// instead of embedding a long-lived project key.
  ///
  /// `emit` is invoked from an arbitrary native thread whenever a token is
  /// needed; it must not block. The host answers out-of-band with
  /// `resolveAuthRequest` / `rejectAuthRequest`.
  public init(projectId: String, baseUrl: String?, emit: @escaping (UInt32) -> Void) throws {
    try Self.ensureModelCacheDir()
    let deviceId = Self.stableDeviceId()
    // Retained deliberately: the native side keeps this pointer for the
    // client's lifetime. Ownership comes back to us on every error path below,
    // and otherwise transfers to close()/release().
    let userData = Unmanaged.passRetained(AuthBridgeBox(emit: emit)).toOpaque()

    var raw: OpaquePointer?
    let status = projectId.withCString { pid in
      withOptionalCString(baseUrl) { base in
        deviceId.withCString { did in
          moss_client_new_with_authenticator_and_device_id(
            pid,
            mossRNAuthNotify,
            userData,
            base,
            did,
            &raw
          )
        }
      }
    }
    if status != 0 {
      Unmanaged<AuthBridgeBox>.fromOpaque(userData).release()
      try Self.throwIfErr(status)
    }
    guard let raw else {
      Unmanaged<AuthBridgeBox>.fromOpaque(userData).release()
      throw Self.mossError(code: -7)
    }
    self.handle = raw
    self.authUserData = userData
    super.init()
  }

  /// Answer a pending auth request with a bearer token (no `Bearer ` prefix —
  /// the native side builds the header). Unknown ids are no-ops natively.
  static func resolveAuthRequest(requestId: UInt32, token: String) throws {
    let status = token.withCString { moss_resolve_auth_request(requestId, $0) }
    try throwIfErr(status)
  }

  /// Fail a pending auth request so the in-flight native call errors out
  /// instead of hanging.
  static func rejectAuthRequest(requestId: UInt32, message: String?) {
    _ = withOptionalCString(message) { moss_reject_auth_request(requestId, $0) }
  }

  deinit {
    close()
  }

  /// Marks the client closed and frees the handle once nothing is using it.
  ///
  /// Never blocks: this is a synchronous `Function` on the JS thread, so
  /// waiting here would freeze the UI for as long as an in-flight
  /// `loadIndex` / query / mutation takes. If calls are still running the
  /// handle is left for the last `release()` to free instead. Either way no
  /// new work can start, since `acquire()` refuses once `closed` is set.
  ///
  /// Safe to call while operations are running, and safe to call twice.
  public func close() {
    state.lock()
    if closed {
      state.unlock()
      return
    }
    closed = true
    guard inFlight == 0 else {
      // Still in use — the last one out owns the teardown.
      state.unlock()
      return
    }
    let doomed = handle
    let doomedAuth = authUserData
    handle = nil
    authUserData = nil
    state.unlock()

    Self.teardown(doomed, doomedAuth)
  }

  /// Frees the native handle, then releases the auth box.
  ///
  /// Order matters: the native side can invoke the notify callback — and so
  /// dereference `user_data` — right up until the client is freed.
  private static func teardown(_ doomed: OpaquePointer?, _ auth: UnsafeMutableRawPointer?) {
    if let doomed {
      moss_client_free(doomed)
    }
    if let auth {
      Unmanaged<AuthBridgeBox>.fromOpaque(auth).release()
    }
  }

  public func createIndex(name: String, docsJson: String, modelId: String?) throws -> [String: Any] {
    try withHandle { h in
      var out: UnsafeMutablePointer<CChar>?
      let status = name.withCString { cname in
        docsJson.withCString { cdocs in
          withOptionalCString(modelId) { cmodel in
            moss_client_create_index_from_json(h, cname, cdocs, cmodel, &out)
          }
        }
      }
      try Self.throwIfErr(status)
      guard let out else {
        throw Self.mossError(code: -7)
      }
      defer { moss_free_string(out) }
      return try Self.decodeJsonObject(String(cString: out))
    }
  }

  public func loadIndex(name: String, options: [String: Any]) throws {
    try withHandle { h in
      let autoRefresh = (options["autoRefresh"] as? Bool) ?? false
      let intervalSeconds = try Self.integerOption(
        options,
        "pollingIntervalSeconds",
        default: 600,
        minimum: 1,
        maximum: Self.maxPollingIntervalSeconds
      )
      let interval = UInt64(intervalSeconds)
      let cachePath = options["cachePath"] as? String

      let status = name.withCString { cname in
        withOptionalCString(cachePath) { cache in
          var nativeOpts = MossLoadIndexOptions(
            auto_refresh: autoRefresh,
            polling_interval_secs: interval,
            cache_path: cache
          )
          var info: UnsafeMutablePointer<MossIndexInfo>?
          let r = moss_client_load_index(h, cname, &nativeOpts, &info)
          if let info { moss_free_index_info(info) }
          return r
        }
      }
      try Self.throwIfErr(status)
    }
  }

  public func unloadIndex(name: String) throws {
    try withHandle { h in
      let status = name.withCString { cname in moss_client_unload_index(h, cname) }
      try Self.throwIfErr(status)
    }
  }

  public func query(name: String, query: String, options: [String: Any]) throws -> [String: Any] {
    try withHandle { h in
      let topK = try Self.integerOption(
        options,
        "topK",
        default: 5,
        minimum: 0,
        maximum: Self.maxTopK
      )
      let alpha = try Self.unitIntervalOption(options, "alpha", default: 0.8)
      let filterJson = options["filterJson"] as? String
      let embedding = try Self.embeddingOption(options, "embedding")

      return try name.withCString { iname in
        try query.withCString { q in
          try withOptionalCString(filterJson) { filter in
            // `embedding` must stay alive for the duration of the call, so the
            // buffer pointer is taken around `invoke` rather than escaping it.
            var result: UnsafeMutablePointer<MossSearchResult>?
            let invoke: (UnsafePointer<Float>?, Int) -> Int32 = { embPtr, embLen in
              var nativeOpts = MossQueryOptions(
                top_k: UInt(topK),
                alpha: alpha,
                filter_json: filter,
                embedding: embPtr,
                embedding_dim: UInt(embLen)
              )
              return moss_client_query(h, iname, q, &nativeOpts, &result)
            }
            let status: Int32 = if let embedding {
              embedding.withUnsafeBufferPointer { bp in invoke(bp.baseAddress, bp.count) }
            } else {
              invoke(nil, 0)
            }
            try Self.throwIfErr(status)
            guard let result else {
              throw Self.mossError(code: -7)
            }
            defer { moss_free_search_result(result) }
            return Self.parseSearchResult(result.pointee)
          }
        }
      }
    }
  }

  public func listIndexes() throws -> [[String: Any]] {
    try withHandle { h in
      var infos: UnsafeMutablePointer<MossIndexInfo>?
      var count: UInt = 0
      let status = moss_client_list_indexes(h, &infos, &count)
      try Self.throwIfErr(status)
      guard let infos else { return [] }
      defer { moss_free_index_info_list(infos, count) }
      var out: [[String: Any]] = []
      out.reserveCapacity(Int(count))
      for i in 0..<Int(count) {
        out.append(Self.parseIndexInfo(infos.advanced(by: i).pointee))
      }
      return out
    }
  }

  public func getIndex(name: String) throws -> [String: Any] {
    try withHandle { h in
      try name.withCString { cname in
        var info: UnsafeMutablePointer<MossIndexInfo>?
        let status = moss_client_get_index(h, cname, &info)
        try Self.throwIfErr(status)
        guard let info else {
          throw Self.mossError(code: -7)
        }
        defer { moss_free_index_info(info) }
        return Self.parseIndexInfo(info.pointee)
      }
    }
  }

  public func deleteIndex(name: String) throws -> Bool {
    try withHandle { h in
      try name.withCString { cname in
        var deleted = false
        let status = moss_client_delete_index(h, cname, &deleted)
        try Self.throwIfErr(status)
        return deleted
      }
    }
  }

  public func addDocs(name: String, docsJson: String, upsert: Bool) throws -> [String: Any] {
    try withHandle { h in
      var out: UnsafeMutablePointer<CChar>?
      let status = name.withCString { cname in
        docsJson.withCString { cdocs in
          moss_client_add_docs_from_json(h, cname, cdocs, upsert, &out)
        }
      }
      try Self.throwIfErr(status)
      guard let out else {
        throw Self.mossError(code: -7)
      }
      defer { moss_free_string(out) }
      return try Self.decodeJsonObject(String(cString: out))
    }
  }

  // MARK: - Internals

  /// Runs `body` with the native handle held open. The handle is not freed
  /// while any such call is in flight, so the pointer stays valid for the whole
  /// call even if `close()` arrives mid-flight. Concurrent operations are still
  /// allowed — the native client is thread-safe.
  private func withHandle<R>(_ body: (OpaquePointer) throws -> R) throws -> R {
    let h = try acquire()
    defer { release() }
    return try body(h)
  }

  private func acquire() throws -> OpaquePointer {
    state.lock()
    defer { state.unlock() }
    guard !closed, let handle else {
      throw Self.mossError(code: -1, message: "MossClient already closed")
    }
    inFlight += 1
    return handle
  }

  private func release() {
    state.lock()
    inFlight -= 1
    // If close() landed while this call was running it deferred teardown to
    // whoever finished last. That is us.
    var doomed: OpaquePointer?
    var doomedAuth: UnsafeMutableRawPointer?
    if inFlight == 0, closed {
      doomed = handle
      doomedAuth = authUserData
      handle = nil
      authUserData = nil
    }
    state.unlock()

    Self.teardown(doomed, doomedAuth)
  }

  /// Upper bound for `topK`. Far above any sane result count, but small enough
  /// that `UInt(_:)` and the engine's own allocation stay well-defined.
  private static let maxTopK = 100_000

  /// Upper bound for `pollingIntervalSeconds` (~136 years). Exactly
  /// representable as a `Double` and safely inside `UInt64`.
  private static let maxPollingIntervalSeconds = Int(UInt32.max)

  private static let cacheDirLock = NSLock()
  private static var cacheDirConfigured = false

  static func setModelCacheDir(_ path: String) throws {
    cacheDirLock.lock()
    defer { cacheDirLock.unlock() }
    let status = path.withCString { moss_set_model_cache_dir($0) }
    try throwIfErr(status)
    cacheDirConfigured = true
  }

  private static func ensureModelCacheDir() throws {
    cacheDirLock.lock()
    defer { cacheDirLock.unlock() }
    if cacheDirConfigured { return }
    guard let cacheRoot = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first else {
      throw mossError(code: -7, message: "could not locate Library/Caches for model cache")
    }
    let dir = cacheRoot.appendingPathComponent("moss-models", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let status = dir.path.withCString { moss_set_model_cache_dir($0) }
    try throwIfErr(status)
    cacheDirConfigured = true
  }

  private static func stableDeviceId() -> String {
    if let idfv = UIDevice.current.identifierForVendor?.uuidString {
      return idfv
    }
    return UUID().uuidString
  }

  // MARK: - Option decoding
  //
  // JS numbers reach us as `Double`, so NaN, ±Infinity, negatives and huge
  // magnitudes are all reachable from user code. `Int(_:)` and `UInt64(_:)`
  // *trap* on those, which kills the app process outright — there is no error
  // to bridge back. Validate first and throw a MossError instead.

  private static func doubleValue(_ raw: Any) -> Double? {
    if let d = raw as? Double { return d }
    if let n = raw as? NSNumber { return n.doubleValue }
    if let i = raw as? Int { return Double(i) }
    return nil
  }

  /// Reads a whole-number option, rejecting anything `Int(_:)` would trap on.
  /// Bounds stay well inside 2^53 so the `Double` comparisons are exact.
  private static func integerOption(
    _ options: [String: Any],
    _ key: String,
    default defaultValue: Int,
    minimum: Int,
    maximum: Int
  ) throws -> Int {
    guard let raw = options[key], !(raw is NSNull) else { return defaultValue }
    guard let value = doubleValue(raw) else {
      throw mossError(code: -2, message: "\(key) must be a number")
    }
    guard value.isFinite else {
      throw mossError(code: -2, message: "\(key) must be a finite number")
    }
    let truncated = value.rounded(.towardZero)
    guard truncated >= Double(minimum), truncated <= Double(maximum) else {
      throw mossError(
        code: -2,
        message: "\(key) must be between \(minimum) and \(maximum), got \(value)"
      )
    }
    return Int(truncated)
  }

  /// Reads a 0...1 weight. `Float(_:)` does not trap on NaN/Infinity, but
  /// forwarding either into the engine is meaningless — reject them here.
  private static func unitIntervalOption(
    _ options: [String: Any],
    _ key: String,
    default defaultValue: Float
  ) throws -> Float {
    guard let raw = options[key], !(raw is NSNull) else { return defaultValue }
    guard let value = doubleValue(raw) else {
      throw mossError(code: -2, message: "\(key) must be a number")
    }
    guard value.isFinite else {
      throw mossError(code: -2, message: "\(key) must be a finite number")
    }
    guard value >= 0, value <= 1 else {
      throw mossError(code: -2, message: "\(key) must be between 0 and 1, got \(value)")
    }
    return Float(value)
  }

  /// Reads a query embedding, rejecting non-finite components before they reach
  /// the engine.
  private static func embeddingOption(_ options: [String: Any], _ key: String) throws -> [Float]? {
    guard let raw = options[key], !(raw is NSNull) else { return nil }
    guard let values = raw as? [Any] else {
      throw mossError(code: -2, message: "\(key) must be an array of numbers")
    }
    if values.isEmpty { return nil }
    var out: [Float] = []
    out.reserveCapacity(values.count)
    for element in values {
      guard let value = doubleValue(element) else {
        throw mossError(code: -2, message: "\(key) must contain only finite numbers")
      }
      // Check finiteness *after* narrowing: a finite Double beyond
      // Float.greatestFiniteMagnitude (~3.4e38) rounds to Float.infinity, so
      // testing the Double alone would still let a non-finite value through.
      let narrowed = Float(value)
      guard narrowed.isFinite else {
        throw mossError(
          code: -2,
          message: "\(key) must contain only values representable as 32-bit floats, got \(value)"
        )
      }
      out.append(narrowed)
    }
    return out
  }

  /// Narrows a bridged JS number to the native request-id type. `UInt32(_:)`
  /// would trap on a negative or oversized value.
  static func authRequestId(_ raw: Int) throws -> UInt32 {
    guard raw >= 0, raw <= Int(UInt32.max) else {
      throw mossError(code: -2, message: "requestId out of range: \(raw)")
    }
    return UInt32(raw)
  }

  static func argumentError(_ message: String) -> NSError {
    mossError(code: -2, message: message)
  }

  private static func throwIfErr(_ status: Int32) throws {
    if status != 0 {
      throw mossError(code: status)
    }
  }

  private static func mossError(code: Int32, message: String? = nil) -> NSError {
    let msg: String
    if let message {
      msg = message
    } else if let ptr = moss_last_error() {
      msg = String(cString: ptr)
    } else {
      msg = "moss native error code \(code)"
    }
    return NSError(
      domain: "dev.moss",
      code: Int(code),
      userInfo: [NSLocalizedDescriptionKey: msg]
    )
  }

  private static func decodeJsonObject(_ json: String) throws -> [String: Any] {
    guard let data = json.data(using: .utf8),
          let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw mossError(code: -7, message: "failed to decode Moss JSON response")
    }
    return [
      "jobId": obj["jobId"] as? String ?? "",
      "indexName": obj["indexName"] as? String ?? "",
      "docCount": obj["docCount"] as? Int ?? 0,
    ]
  }

  /// Nullable C strings are omitted rather than boxed with `as Any` — that
  /// would put an `Optional.none` into the dictionary and hand a non-JSON value
  /// to the bridge. Absent keys read as `undefined` in JS, which the optional
  /// fields on `IndexInfo` / `ModelRef` already allow.
  private static func parseIndexInfo(_ info: MossIndexInfo) -> [String: Any] {
    var model: [String: Any] = ["id": cstr(info.model.id)]
    if let version = cstrOpt(info.model.version) {
      model["version"] = version
    }

    var out: [String: Any] = [
      "id": cstr(info.id),
      "name": cstr(info.name),
      "status": cstr(info.status),
      "docCount": Int(info.doc_count),
      "model": model,
    ]
    if let version = cstrOpt(info.version) {
      out["version"] = version
    }
    if let createdAt = cstrOpt(info.created_at) {
      out["createdAt"] = createdAt
    }
    if let updatedAt = cstrOpt(info.updated_at) {
      out["updatedAt"] = updatedAt
    }
    return out
  }

  private static func parseSearchResult(_ result: MossSearchResult) -> [String: Any] {
    let count = Int(result.doc_count)
    var docs: [[String: Any]] = []
    docs.reserveCapacity(count)
    if let buf = result.docs {
      for i in 0..<count {
        let d = buf.advanced(by: i).pointee
        var row: [String: Any] = [
          "id": cstr(d.id),
          "text": cstr(d.text),
          "score": d.score,
        ]
        if let metadata = parseMetadata(d.metadata, count: d.metadata_count) {
          row["metadata"] = metadata
        }
        if let payload = d.payload {
          row["payload"] = String(cString: payload)
        }
        docs.append(row)
      }
    }
    return [
      "docs": docs,
      "query": cstr(result.query),
      "timeMs": result.time_taken_ms,
    ]
  }

  private static func parseMetadata(
    _ entries: UnsafeMutablePointer<MossMetadataEntry>?,
    count: UInt
  ) -> [String: String]? {
    guard let entries, count > 0 else { return nil }
    var out: [String: String] = [:]
    for i in 0..<Int(count) {
      let e = entries.advanced(by: i).pointee
      guard let keyPtr = e.key else { continue }
      out[String(cString: keyPtr)] = cstr(e.value)
    }
    return out.isEmpty ? nil : out
  }
}

@inline(__always)
func withOptionalCString<R>(_ value: String?, _ body: (UnsafePointer<CChar>?) throws -> R) rethrows -> R {
  if let value {
    return try value.withCString { try body($0) }
  }
  return try body(nil)
}

@inline(__always)
func cstr(_ ptr: UnsafeMutablePointer<CChar>?) -> String {
  ptr.flatMap { String(cString: $0) } ?? ""
}

@inline(__always)
func cstrOpt(_ ptr: UnsafeMutablePointer<CChar>?) -> String? {
  ptr.flatMap { String(cString: $0) }
}
