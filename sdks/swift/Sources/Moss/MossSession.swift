import Foundation
import MossC

public final class MossSessionEmbedding: @unchecked Sendable {
    fileprivate let handle: OpaquePointer
    private let freeEmbedding: MossSessionBoundEmbeddingFreeFunction

    fileprivate init(
        handle: OpaquePointer,
        freeEmbedding: @escaping MossSessionBoundEmbeddingFreeFunction
    ) {
        self.handle = handle
        self.freeEmbedding = freeEmbedding
    }

    deinit {
        freeEmbedding(handle)
    }
}

/// On-device session handle for a single index. Returned by
/// `MossClient.session(_:options:)`. All embedding runs locally with
/// the session's model (`moss-minilm` unless `SessionOptions.modelId`
/// says otherwise); queries don't hit the network.
///
/// ```swift
/// let session = try await client.session("notes")
/// _ = try await session.addDocs([
///     DocumentInfo(id: "1", text: "first note"),
///     DocumentInfo(id: "2", text: "second note"),
/// ])
/// let result = try await session.query("first")
/// ```
///
/// The class is thread-safe: concurrent calls are serialized only at
/// the native handle level. `close()` (called automatically on deinit)
/// blocks until every in-flight call has returned before freeing the
/// native pointer, mirroring the contract in `MossClient.close()`.
public final class MossSession: @unchecked Sendable {
    private var handle: OpaquePointer?
    /// The client's authenticator, which the native session can call until `moss_session_free`.
    private var authBox: AuthenticatorBox?
    private var inFlight: Int = 0
    private var closed: Bool = false
    private let stateCond = NSCondition()

    /// Used by `MossClient.session(...)` only. The C API hands over a
    /// strong, transferable pointer, and the session takes exclusive ownership.
    init(takingOwnershipOf raw: OpaquePointer, authBox: AuthenticatorBox?) {
        self.handle = raw
        self.authBox = authBox
    }

    public static var supportsIdentityBoundTextInference: Bool {
        MossIdentityBoundSessionAPI.shared != nil
    }

    static func requireIdentityBoundTextInference(
        supported: Bool = supportsIdentityBoundTextInference
    ) throws {
        guard supported else {
            throw MossError(
                code: MossError.modelUnavailable,
                message: "This Moss native runtime does not expose the identity-bound session API; update Moss.xcframework"
            )
        }
    }

    deinit { close() }

    /// Send the final usage telemetry, then free the underlying native handle.
    /// Idempotent. Blocks until all in-flight calls return, so they never operate
    /// on a freed pointer, then until the telemetry is delivered or 2 seconds pass.
    public func close() {
        stateCond.lock()
        if closed {
            stateCond.unlock()
            return
        }
        closed = true
        while inFlight > 0 {
            stateCond.wait()
        }
        let h = handle
        handle = nil
        let box = authBox
        authBox = nil
        stateCond.unlock()
        withExtendedLifetime(box) {
            if let h { moss_session_free(h) }
        }
    }

    // ── Identity ─────────────────────────────────────────────────────

    /// The index name this session was opened against.
    public var name: String {
        // Synchronously borrow — `moss_session_name` returns a pointer
        // into native-owned memory; we copy into a Swift String before
        // returning the borrow.
        guard let h = try? borrowHandle() else { return "" }
        defer { returnHandle() }
        let ptr = moss_session_name(h)
        guard let ptr else { return "" }
        return String(cString: ptr)
    }

    /// Current document count in the index.
    public var docCount: Int {
        guard let h = try? borrowHandle() else { return 0 }
        defer { returnHandle() }
        return Int(moss_session_doc_count(h))
    }

    // ── Mutations ────────────────────────────────────────────────────

    /// Add or upsert documents. Returns (added, updated) counts —
    /// `added` is rows that didn't exist before, `updated` is rows
    /// whose id collided with an existing row.
    @discardableResult
    public func addDocs(
        _ docs: [DocumentInfo],
        upsert: Bool = true
    ) async throws -> (added: Int, updated: Int) {
        try MossClient.requireNoNul(docIds: docs.map(\.id))
        guard MossIdentityBoundSessionAPI.shared != nil else {
            throw MossError(
                code: MossError.modelUnavailable,
                message: "This Moss native runtime cannot safely open provenance-sensitive sessions"
            )
        }
        return try await Task.detached { [self] () throws -> (Int, Int) in
            let h = try borrowHandle()
            defer { returnHandle() }
            return try Self.withNativeDocs(docs) { docBuf, count in
                var opts = MossAddDocsOptions(upsert: upsert)
                var added: UInt = 0
                var updated: UInt = 0
                let r = moss_session_add_docs(h, docBuf, count, &opts, &added, &updated)
                try MossClient.throwIfErr(r)
                return (Int(added), Int(updated))
            }
        }.value
    }

    /// Delete documents by id. Returns the actual count deleted —
    /// missing ids are silently ignored.
    @discardableResult
    public func deleteDocs(_ docIds: [String]) async throws -> Int {
        try MossClient.requireNoNul(docIds: docIds)
        return try await Task.detached { [self] () throws -> Int in
            let h = try borrowHandle()
            defer { returnHandle() }
            return try withCStringArray(docIds) { ptrs in
                var deleted: UInt = 0
                let r = moss_session_delete_docs(h, ptrs, UInt(docIds.count), &deleted)
                try MossClient.throwIfErr(r)
                return Int(deleted)
            }
        }.value
    }

    /// Deterministic fetch — no embedding, no similarity ranking. Returns docs
    /// by exact id and/or a metadata predicate, optionally sorted and collapsed
    /// by parent unit. See [GetDocsOptions].
    public func getDocs(options: GetDocsOptions) async throws -> [DocumentInfo] {
        try MossClient.requireNoNul(docIds: options.ids ?? [])
        let opts = options
        return try await Task.detached { [self] () throws -> [DocumentInfo] in
            let h = try borrowHandle()
            defer { returnHandle() }
            return try Self.runGetDocs(h, options: opts)
        }.value
    }

    /// Return documents by id, in the order requested. Passing nil returns all
    /// docs (convenient for inspection, expensive on large indexes). An empty
    /// array returns nothing (vs nil's "everything").
    public func getDocs(_ docIds: [String]? = nil) async throws -> [DocumentInfo] {
        try await getDocs(options: GetDocsOptions(ids: docIds))
    }

    /// Fetch exact ids, returned in the order requested.
    public func getDocs(ids: [String]) async throws -> [DocumentInfo] {
        try await getDocs(options: GetDocsOptions(ids: ids))
    }

    /// Fetch by a metadata predicate — deterministic, ordered, no query vector.
    public func getDocs(
        where filter: Filter, sortBy: String? = nil, ascending: Bool = true
    ) async throws -> [DocumentInfo] {
        try await getDocs(options: GetDocsOptions(
            filter: filter, sortBy: sortBy, ascending: ascending))
    }

    private static func runGetDocs(
        _ h: OpaquePointer,
        options: GetDocsOptions
    ) throws -> [DocumentInfo] {
        // An explicit empty id list fetches nothing (vs nil = all docs).
        if let ids = options.ids, ids.isEmpty { return [] }
        var filterJson: String? = nil
        if let f = options.filter {
            guard let encoded = f.encoded() else {
                throw MossError(code: MossError.invalidArgument, message: "could not encode metadata filter")
            }
            filterJson = encoded
        }
        let group = options.groupByParent

        func call(
            _ idsPtr: UnsafePointer<UnsafePointer<CChar>?>?, _ idCount: UInt
        ) throws -> [DocumentInfo] {
            try withOptionalCString(filterJson) { filterC in
                try withOptionalCString(options.sortBy) { sortC in
                    try withOptionalCString(group?.parentField) { parentC in
                        try withOptionalCString(group?.orderField) { orderC in
                            var outDocs: UnsafeMutablePointer<MossDocumentInfo>?
                            var outCount: UInt = 0
                            guard let api = MossIdentityBoundSessionAPI.shared else {
                                throw MossError(
                                    code: MossError.modelUnavailable,
                                    message: "This Moss native runtime cannot safely open provenance-sensitive sessions"
                                )
                            }
                            let r = api.getDocs(
                                h, idsPtr, idCount, filterC, sortC,
                                options.ascending, parentC, orderC,
                                &outDocs, &outCount
                            )
                            try MossClient.throwIfErr(r)
                            guard let outDocs else { return [] }
                            defer { moss_free_documents(outDocs, outCount) }
                            return parseDocuments(outDocs, count: outCount)
                        }
                    }
                }
            }
        }

        if let ids = options.ids {
            return try withCStringArray(ids) { ptrs in
                try call(ptrs, UInt(ids.count))
            }
        }
        return try call(nil, 0)
    }

    // ── Query ────────────────────────────────────────────────────────

    /// Run the on-device embedding model on `text` and return the
    /// raw 384-dim FP32 vector. Useful for two patterns:
    /// 1. Latency benches that want to time embedding vs search
    ///    separately (pair with `query(_:embedding:options:)`).
    /// 2. Querying the same input across multiple indexes without
    ///    paying the embedding cost N times.
    ///
    @available(*, deprecated, message: "Raw embeddings do not carry model identity; use embedBound(_:)")
    public func embed(_ text: String) async throws -> [Float] {
        try Self.requireIdentityBoundTextInference()
        return try await Task.detached { [self] () throws -> [Float] in
            let h = try borrowHandle()
            defer { returnHandle() }
            return try text.withCString { ctext in
                var buf = [Float](repeating: 0, count: 1024)
                var outDim: UInt = 0
                let r = buf.withUnsafeMutableBufferPointer { bp in
                    moss_session_embed_query(h, ctext, bp.baseAddress, UInt(bp.count), &outDim)
                }
                try MossClient.throwIfErr(r)
                buf.removeSubrange(Int(outDim)..<buf.count)
                return buf
            }
        }.value
    }

    public func embedBound(_ text: String) async throws -> MossSessionEmbedding {
        try Self.requireIdentityBoundTextInference()
        return try await Task.detached { [self] () throws -> MossSessionEmbedding in
            let h = try borrowHandle()
            defer { returnHandle() }
            guard let api = MossIdentityBoundSessionAPI.shared else {
                throw MossError(code: MossError.modelUnavailable, message: "Identity-bound inference is unavailable")
            }
            return try text.withCString { ctext in
                var embedding: OpaquePointer?
                try MossClient.throwIfErr(api.embed(h, ctext, &embedding))
                guard let embedding else { throw MossClient.missingResult() }
                return MossSessionEmbedding(
                    handle: embedding,
                    freeEmbedding: api.freeEmbedding
                )
            }
        }.value
    }

    public func query(
        _ q: String,
        options: QueryOptions = QueryOptions()
    ) async throws -> SearchResult {
        try await query(q, embedding: nil, boundEmbedding: nil, options: options)
    }

    public func query(
        _ q: String,
        embedding: MossSessionEmbedding,
        options: QueryOptions = QueryOptions()
    ) async throws -> SearchResult {
        try await query(q, embedding: nil, boundEmbedding: embedding, options: options)
    }

    /// Search variant that takes a pre-computed embedding (typically
    /// obtained from `embed(_:)`). Bypasses the model forward pass —
    /// pure dot-product scan + top-k. The `text` parameter is still
    /// passed through to telemetry / SearchResult.query so the
    /// caller-visible result stays consistent with `query(_:)`.
    @available(*, deprecated, message: "Raw embeddings do not carry model identity; use MossSessionEmbedding")
    public func query(
        _ q: String,
        embedding: [Float]?,
        options: QueryOptions = QueryOptions()
    ) async throws -> SearchResult {
        try await query(q, embedding: embedding, boundEmbedding: nil, options: options)
    }

    private func query(
        _ q: String,
        embedding: [Float]?,
        boundEmbedding: MossSessionEmbedding?,
        options: QueryOptions
    ) async throws -> SearchResult {
        let opts = options
        guard opts.topK >= 0 else {
            throw MossError(code: MossError.invalidArgument, message: "topK must be non-negative; got \(opts.topK)")
        }
        try Self.requireIdentityBoundTextInference()
        return try await Task.detached { [self] () throws -> SearchResult in
            let h = try borrowHandle()
            defer { returnHandle() }
            // Typed filter takes precedence over the legacy JSON string;
            // surface an encode failure rather than silently dropping the filter.
            var filterJson = opts.filterJson
            if let f = opts.filter {
                guard let encoded = f.encoded() else {
                    throw MossError(code: MossError.invalidArgument, message: "could not encode metadata filter")
                }
                filterJson = encoded
            }
            let group = opts.groupByParent
            return try q.withCString { cq in
                try withOptionalCString(filterJson) { filter in
                    try withOptionalCString(group?.parentField) { parentC in
                        try withOptionalCString(group?.orderField) { orderC in
                            // `embedding` is captured by-ref; give it a stable
                            // pointer for the C call via withUnsafeBufferPointer.
                            let result: UnsafeMutablePointer<MossSearchResult>? = try {
                                var resultLocal: UnsafeMutablePointer<MossSearchResult>?
                                var nativeOpts = MossQueryOptions(
                                    top_k: UInt(opts.topK),
                                    alpha: opts.alpha,
                                    filter_json: filter,
                                    embedding: nil,
                                    embedding_dim: 0
                                )
                                let r: Int32
                                guard let api = MossIdentityBoundSessionAPI.shared else {
                                    throw MossError(
                                        code: MossError.modelUnavailable,
                                        message: "This Moss native runtime cannot safely open provenance-sensitive sessions"
                                    )
                                }
                                if let boundEmbedding {
                                    r = api.queryBound(
                                        h, cq, boundEmbedding.handle, &nativeOpts,
                                        parentC, orderC, &resultLocal
                                    )
                                } else if let emb = embedding {
                                    r = emb.withUnsafeBufferPointer { bp in
                                        nativeOpts.embedding = bp.baseAddress
                                        nativeOpts.embedding_dim = UInt(bp.count)
                                        return api.query(
                                            h, cq, &nativeOpts, parentC, orderC, &resultLocal
                                        )
                                    }
                                } else {
                                    r = api.query(
                                        h, cq, &nativeOpts, parentC, orderC, &resultLocal
                                    )
                                }
                                try MossClient.throwIfErr(r)
                                return resultLocal
                            }()
                            guard let result else { throw MossClient.missingResult() }
                            defer { moss_free_search_result(result) }
                            return MossClient.parseSearchResult(result.pointee)
                        }
                    }
                }
            }
        }.value
    }

    func queryWithModelIdentity(
        _ q: String,
        embedding: [Float],
        modelId: String,
        modelArtifactVersion: String,
        manifestSha256: String,
        options: QueryOptions = QueryOptions()
    ) async throws -> SearchResult {
        let opts = options
        guard opts.topK >= 0 else {
            throw MossError(code: MossError.invalidArgument, message: "topK must be non-negative; got \(opts.topK)")
        }
        try Self.requireIdentityBoundTextInference()
        return try await Task.detached { [self] () throws -> SearchResult in
            let h = try borrowHandle()
            defer { returnHandle() }
            var filterJson = opts.filterJson
            if let filter = opts.filter {
                guard let encoded = filter.encoded() else {
                    throw MossError(code: MossError.invalidArgument, message: "could not encode metadata filter")
                }
                filterJson = encoded
            }
            let group = opts.groupByParent
            return try q.withCString { queryCString in
                try withOptionalCString(filterJson) { filterCString in
                    try withOptionalCString(group?.parentField) { parentCString in
                        try withOptionalCString(group?.orderField) { orderCString in
                            guard let api = MossIdentityBoundSessionAPI.shared else {
                                throw MossError(
                                    code: MossError.modelUnavailable,
                                    message: "This Moss native runtime cannot safely open provenance-sensitive sessions"
                                )
                            }
                            var result: UnsafeMutablePointer<MossSearchResult>?
                            var nativeOptions = MossQueryOptions(
                                top_k: UInt(opts.topK),
                                alpha: opts.alpha,
                                filter_json: filterCString,
                                embedding: nil,
                                embedding_dim: 0
                            )
                            let callResult = embedding.withUnsafeBufferPointer { buffer in
                                nativeOptions.embedding = buffer.baseAddress
                                nativeOptions.embedding_dim = UInt(buffer.count)
                                return modelId.withCString { modelCString in
                                    modelArtifactVersion.withCString { versionCString in
                                        manifestSha256.withCString { digestCString in
                                            api.queryWithModelIdentity(
                                                h,
                                                queryCString,
                                                &nativeOptions,
                                                modelCString,
                                                versionCString,
                                                digestCString,
                                                parentCString,
                                                orderCString,
                                                &result
                                            )
                                        }
                                    }
                                }
                            }
                            try MossClient.throwIfErr(callResult)
                            guard let result else { throw MossClient.missingResult() }
                            defer { moss_free_search_result(result) }
                            return MossClient.parseSearchResult(result.pointee)
                        }
                    }
                }
            }
        }.value
    }

    // ── Persistence ──────────────────────────────────────────────────

    /// Pull a server-side index into this session. Returns the doc count
    /// loaded (0 if the cloud has no index by that name).
    ///
    /// By default this is a one-time hydration: the session then behaves as a
    /// local one — add/delete/query don't hit the network. Pass
    /// `options.autoRefresh = true` to keep it in sync: a background task
    /// polls the cloud index every `options.pollingIntervalSeconds` and pulls
    /// newer versions in on the next `query`/`getDocs`/`docCount`. Auto-refresh
    /// pauses while the session has un-pushed local edits (`addDocs`/`deleteDocs`
    /// before a `pushIndex`), so it never clobbers local work.
    ///
    /// For on-disk persistence of a session, use `save(toCachePath:)` /
    /// `loadFromDisk(cachePath:)`. `options.cachePath` applies to
    /// `MossClient.loadIndex`, not to sessions, so it is not forwarded here.
    @discardableResult
    public func loadIndex(
        _ indexName: String,
        options: LoadIndexOptions = LoadIndexOptions()
    ) async throws -> Int {
        try MossClient.requireNoNul(inIndexNames: [indexName])
        let opts = options
        return try await Task.detached { [self] () throws -> Int in
            let h = try borrowHandle()
            defer { returnHandle() }
            return try indexName.withCString { cname in
                // `cachePath` is intentionally not forwarded: the native session
                // load ignores it (sessions persist via `save(toCachePath:)`),
                // so passing it would only mislead callers.
                var nativeOpts = MossLoadIndexOptions(
                    auto_refresh: opts.autoRefresh,
                    polling_interval_secs: opts.pollingIntervalSeconds,
                    cache_path: nil
                )
                var docCount: UInt = 0
                let r = moss_session_load_index(h, cname, &nativeOpts, &docCount)
                try MossClient.throwIfErr(r)
                return Int(docCount)
            }
        }.value
    }

    /// Persist this session's index to disk at `cachePath`. Writes
    /// vectors, documents, and metadata atomically so the session can
    /// be re-opened via `loadFromDisk` on the next app launch without
    /// re-embedding. Vector precision matches the `vectorQuantization`
    /// passed to `MossClient.session(_:options:)`.
    ///
    /// With `cachePath` nil the snapshot goes in `sessions/<project id>/`
    /// under the `MOSS_SESSION_CACHE_PATH` environment variable, which only
    /// session snapshots read, or else in the app's cache directory, at
    /// `Library/Caches/moss/sessions/<project id>/`, which the system may purge.
    public func save(toCachePath cachePath: String? = nil) async throws {
        try await Task.detached { [self] () throws -> Void in
            let h = try borrowHandle()
            defer { returnHandle() }
            try withOptionalCString(cachePath) { cpath in
                let r = moss_session_save_to_disk(h, cpath)
                try MossClient.throwIfErr(r)
            }
        }.value
    }

    /// Restore a session from a previous `save(toCachePath:)` at
    /// `cachePath`, or with `cachePath` nil from the directory that a
    /// `save(toCachePath:)` without one picks. Returns the doc count restored.
    ///
    /// The session adopts the model the snapshot records, except that a
    /// session opened with `modelId: "custom"` and `autoLoadOnInit: false`
    /// loads a foundation snapshot as `custom` until `loadIndex` succeeds in it.
    ///
    /// Note: the session's *name* (passed to `client.session(_:)`) must
    /// match the one used at save time — it's part of the on-disk
    /// directory path.
    @discardableResult
    public func loadFromDisk(cachePath: String? = nil) async throws -> Int {
        try await Task.detached { [self] () throws -> Int in
            let h = try borrowHandle()
            defer { returnHandle() }
            return try withOptionalCString(cachePath) { cpath in
                var docCount: UInt = 0
                let r = moss_session_load_from_disk(h, cpath, &docCount)
                try MossClient.throwIfErr(r)
                return Int(docCount)
            }
        }.value
    }

    /// Push the in-memory session to the cloud as a server-side index.
    /// Returns the push job details for status tracking.
    public func pushIndex() async throws -> PushIndexResult {
        try await Task.detached { [self] () throws -> PushIndexResult in
            let h = try borrowHandle()
            defer { returnHandle() }
            var raw: UnsafeMutablePointer<MossPushIndexResult>?
            let r = moss_session_push_index(h, &raw)
            try MossClient.throwIfErr(r)
            guard let raw else { throw MossClient.missingResult() }
            defer { moss_free_push_index_result(raw) }
            let p = raw.pointee
            return PushIndexResult(
                jobId: cstr(p.job_id),
                indexName: cstr(p.index_name),
                docCount: Int(p.doc_count),
                status: cstr(p.status)
            )
        }.value
    }

    // ── Internals ────────────────────────────────────────────────────

    private func borrowHandle() throws -> OpaquePointer {
        stateCond.lock()
        defer { stateCond.unlock() }
        guard !closed, let h = handle else {
            throw MossError(code: MossError.nullPointer, message: "MossSession already closed")
        }
        inFlight += 1
        return h
    }

    private func returnHandle() {
        stateCond.lock()
        defer { stateCond.unlock() }
        inFlight -= 1
        if inFlight == 0 {
            stateCond.broadcast()
        }
    }

    /// Wrap a `[DocumentInfo]` as a contiguous `MossDocumentInfo *`
    /// buffer for the native call, then dispose of the temporary
    /// allocations once `body` returns.
    private static func withNativeDocs<R>(
        _ docs: [DocumentInfo],
        _ body: (UnsafePointer<MossDocumentInfo>?, UInt) throws -> R
    ) throws -> R {
        if docs.isEmpty {
            return try body(nil, 0)
        }

        // Allocate one CString per id/text and one Float buffer per
        // optional embedding. Track them so we can free in any order
        // (errors thrown from `body` still hit the deferred cleanup).
        var idHolders: [UnsafeMutablePointer<CChar>] = []
        var textHolders: [UnsafeMutablePointer<CChar>] = []
        var embHolders: [UnsafeMutablePointer<Float>] = []
        var metaHolders: [UnsafeMutablePointer<MossMetadataEntry>] = []
        var metaKVHolders: [UnsafeMutablePointer<CChar>] = []
        var payloadHolders: [UnsafeMutablePointer<CChar>] = []

        defer {
            for p in idHolders { free(p) }
            for p in textHolders { free(p) }
            for p in embHolders { p.deallocate() }
            for p in metaHolders { p.deallocate() }
            for p in metaKVHolders { free(p) }
            for p in payloadHolders { free(p) }
        }

        var native: [MossDocumentInfo] = []
        native.reserveCapacity(docs.count)

        for d in docs {
            let idPtr = strdup(d.id)!
            let textPtr = strdup(d.text)!
            idHolders.append(idPtr)
            textHolders.append(textPtr)

            var embPtr: UnsafeMutablePointer<Float>? = nil
            var embLen: UInt = 0
            if let e = d.embedding, !e.isEmpty {
                let buf = UnsafeMutablePointer<Float>.allocate(capacity: e.count)
                buf.initialize(from: e, count: e.count)
                embHolders.append(buf)
                embPtr = buf
                embLen = UInt(e.count)
            }

            var metaPtr: UnsafeMutablePointer<MossMetadataEntry>? = nil
            var metaCount: UInt = 0
            if let m = d.metadata, !m.isEmpty {
                let buf = UnsafeMutablePointer<MossMetadataEntry>.allocate(capacity: m.count)
                metaHolders.append(buf)
                var i = 0
                for (k, v) in m {
                    let kPtr = strdup(k)!
                    let vPtr = strdup(v)!
                    metaKVHolders.append(kPtr)
                    metaKVHolders.append(vPtr)
                    buf.advanced(by: i).initialize(to: MossMetadataEntry(
                        key: kPtr,
                        value: vPtr
                    ))
                    i += 1
                }
                metaPtr = buf
                metaCount = UInt(m.count)
            }

            var payloadPtr: UnsafeMutablePointer<CChar>? = nil
            if let p = d.payload {
                let pp = strdup(p)!
                payloadHolders.append(pp)
                payloadPtr = pp
            }

            var nativeDoc = MossDocumentInfo()
            nativeDoc.id = idPtr
            nativeDoc.text = textPtr
            nativeDoc.metadata = metaPtr
            nativeDoc.metadata_count = metaCount
            nativeDoc.embedding = embPtr
            nativeDoc.embedding_dim = embLen
            nativeDoc.payload = payloadPtr
            native.append(nativeDoc)
        }

        return try native.withUnsafeBufferPointer { buf in
            try body(buf.baseAddress, UInt(buf.count))
        }
    }

    private static func parseDocuments(
        _ ptr: UnsafeMutablePointer<MossDocumentInfo>,
        count: UInt
    ) -> [DocumentInfo] {
        let n = Int(count)
        var out: [DocumentInfo] = []
        out.reserveCapacity(n)
        for i in 0..<n {
            let d = ptr.advanced(by: i).pointee
            let metadata = MossClient.parseMetadata(
                d.metadata,
                count: d.metadata_count
            )
            var embedding: [Float]? = nil
            if let e = d.embedding, d.embedding_dim > 0 {
                embedding = Array(UnsafeBufferPointer(start: e, count: Int(d.embedding_dim)))
            }
            out.append(DocumentInfo(
                id: cstr(d.id),
                text: cstr(d.text),
                metadata: metadata,
                embedding: embedding,
                payload: d.payload.map { String(cString: $0) }
            ))
        }
        return out
    }
}

/// Result of pushing a local session to the cloud via
/// `MossSession.pushIndex()`. Status starts as `"queued"` and becomes
/// `"ready"` once the server-side processing job completes; poll
/// `MossClient.getJobStatus(jobId)` to track progress.
public struct PushIndexResult: Sendable {
    public let jobId: String
    public let indexName: String
    public let docCount: Int
    public let status: String
}
