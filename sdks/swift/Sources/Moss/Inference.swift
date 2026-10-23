import Foundation

/// A client for OpenAI-compatible chat completions that answer from your Moss indexes.
///
/// It holds the project credentials, your provider key and the limits of each call,
/// and keeps its own connections to the Moss inference gateway. `chat.completions.create`
/// returns the whole reply, and `createStreaming` returns it chunk by chunk. A call never follows
/// a redirect: it fails with the 3xx status instead, so the project credentials never reach another URL.
public final class MossInference: Sendable {
    /// The base URL of the Moss inference gateway, unless `MOSS_INFERENCE_URL` sets another.
    static let defaultBaseURL = "https://inference.moss.dev/v1"
    /// How long a call may take to connect and send its request.
    static let connectTimeout: TimeInterval = 10
    /// The URLSession wait that stands for no limit.
    static let noLimit: TimeInterval = 7 * 24 * 3600

    let url: URL
    let headers: [String: String]
    let timeout: TimeInterval?
    let idleTimeout: TimeInterval?
    let maxRetries: Int
    /// The session of every call, with room for 64 streams to one host,
    /// since a call that waits for a free connection uses up its connect limit.
    /// Its request timeout is 60 seconds because URLSession reads a request's 60,
    /// the default, as unset and takes the session's value, so an idle limit of 60 holds.
    let session: URLSession

    /// Creates a client, or throws `InferenceError` for a bad credential, key, limit or gateway URL.
    ///
    /// Calls go to `https://inference.moss.dev/v1`, or to the base URL in `MOSS_INFERENCE_URL`.
    /// `apiKey` is optional: your own OpenAI, Anthropic
    /// or Google key, for a vendor model such as `gpt-4o-mini`. `moss` ignores it, and a vendor model without one is refused.
    /// `idleTimeout` ends a call when the gateway sends nothing for that many seconds, before the reply or between any two of its bytes.
    /// `timeout` limits each whole call, stream included. For either limit, `nil` or `.infinity` means none, the default for `timeout`.
    /// `maxRetries` (0 for none) sends a call again after a connection failure or a status of 408, 409, 429 or 500 and above,
    /// waiting a `Retry-After` of 60 seconds or less, else a backoff from 0.5 up to 8 seconds, within `timeout`. A stream that started is never retried.
    public init(
        projectId: String,
        projectKey: String,
        apiKey: String? = nil,
        timeout: TimeInterval? = nil,
        idleTimeout: TimeInterval? = 120,
        maxRetries: Int = 2
    ) throws {
        try Self.checkValue("projectId", projectId)
        try Self.checkValue("projectKey", projectKey)
        try apiKey.map { try Self.checkValue("apiKey", $0) }
        if projectId.contains(":") { throw InferenceError.invalidRequest("projectId must not contain ':'") }
        url = try Self.endpoint(ProcessInfo.processInfo.environment["MOSS_INFERENCE_URL"])
        self.timeout = try Self.limit(timeout, "timeout")
        self.idleTimeout = try Self.limit(idleTimeout, "idleTimeout")
        self.maxRetries = try Self.retries(maxRetries)
        var headers = [
            "Authorization": "Bearer \(projectId):\(projectKey)", "Content-Type": "application/json", "Accept": "text/event-stream",
        ]
        headers["X-Moss-Provider-Key"] = apiKey
        self.headers = headers
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 60
        configuration.httpMaximumConnectionsPerHost = 64
        configuration.urlCache = nil
        session = URLSession(configuration: configuration)
    }

    deinit { session.finishTasksAndInvalidate() }

    /// The chat API, as in OpenAI's `client.chat.completions`.
    public var chat: Chat { Chat(completions: Completions(client: self)) }

    public struct Chat: Sendable { public let completions: Completions }

    /// Chat completions in the shape of OpenAI's `chat.completions`.
    ///
    /// `tools` offers functions you run and MCP servers the gateway calls, and `toolChoice` and `parallelToolCalls`
    /// steer them. Each is sent only when given and wins over the same key in `extra`, which holds the other OpenAI body fields.
    /// `indexes` names the indexes to search, all of the project's when `nil` and none when empty, as with `retrieve: false`.
    /// Moss can answer an identical request from its reply cache, and `cache: false` always asks the model.
    /// `model` is `moss`, Moss's model, unless you name a vendor model such as `gpt-4o-mini`.
    /// `apiKey` replaces the client's provider key for one call, and an empty one is refused.
    /// `timeout`, `idleTimeout` and `maxRetries` replace the client's for one call. `nil` keeps the client's, and `.infinity` lifts a limit.
    public struct Completions: Sendable {
        let client: MossInference

        /// Runs a chat completion and returns the whole reply.
        public func create(
            model: String = "moss",
            messages: [ChatMessage],
            tools: [Tool] = [],
            toolChoice: ToolChoice? = nil,
            parallelToolCalls: Bool? = nil,
            indexes: [String]? = nil,
            retrieve: Bool = true,
            cache: Bool = true,
            apiKey: String? = nil,
            timeout: TimeInterval? = nil,
            idleTimeout: TimeInterval? = nil,
            maxRetries: Int? = nil,
            extra: [String: JSONValue] = [:]
        ) async throws -> ChatCompletion {
            let stream = try await createStreaming(
                model: model, messages: messages, tools: tools, toolChoice: toolChoice, parallelToolCalls: parallelToolCalls,
                indexes: indexes, retrieve: retrieve, cache: cache, apiKey: apiKey, timeout: timeout, idleTimeout: idleTimeout,
                maxRetries: maxRetries, extra: extra
            )
            return try await ChatCompletion(gathering: stream, model: model)
        }

        /// Runs a chat completion and returns its chunks as they arrive.
        public func createStreaming(
            model: String = "moss",
            messages: [ChatMessage],
            tools: [Tool] = [],
            toolChoice: ToolChoice? = nil,
            parallelToolCalls: Bool? = nil,
            indexes: [String]? = nil,
            retrieve: Bool = true,
            cache: Bool = true,
            apiKey: String? = nil,
            timeout: TimeInterval? = nil,
            idleTimeout: TimeInterval? = nil,
            maxRetries: Int? = nil,
            extra: [String: JSONValue] = [:]
        ) async throws -> ChatCompletionStream {
            if let name = indexes?.first(where: { $0.isEmpty || $0.contains(",") }) {
                throw InferenceError.invalidRequest("Index names must not be empty or contain ',': \"\(name)\"")
            }
            try indexes?.forEach { try MossInference.checkHeader("Index names", $0) }
            try apiKey.map { try MossInference.checkValue("apiKey", $0) }
            let timeout = try timeout.map { try MossInference.limit($0, "timeout") } ?? client.timeout
            let idleTimeout = try idleTimeout.map { try MossInference.limit($0, "idleTimeout") } ?? client.idleTimeout
            let maxRetries = try maxRetries.map(MossInference.retries) ?? client.maxRetries
            var body = extra
            if !tools.isEmpty { body["tools"] = .array(tools.map(\.json)) }
            if let toolChoice { body["tool_choice"] = toolChoice.json }
            if let parallelToolCalls { body["parallel_tool_calls"] = .bool(parallelToolCalls) }
            body["model"] = .string(model)
            body["messages"] = .array(messages.map(\.json))
            body["stream"] = true
            var request = URLRequest(
                url: client.url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: idleTimeout ?? MossInference.noLimit
            )
            request.httpMethod = "POST"
            request.httpBody = try JSONEncoder().encode(body)
            client.headers.forEach { request.setValue($0.value, forHTTPHeaderField: $0.key) }
            if let indexes, !indexes.isEmpty { request.setValue(indexes.joined(separator: ","), forHTTPHeaderField: "X-Moss-Indexes") }
            if !retrieve || indexes?.isEmpty == true { request.setValue("off", forHTTPHeaderField: "X-Moss-Retrieve") }
            if !cache { request.setValue("off", forHTTPHeaderField: "X-Moss-Cache") }
            if let apiKey { request.setValue(apiKey, forHTTPHeaderField: "X-Moss-Provider-Key") }
            return try await ChatCompletionStream.open(
                request, in: client.session, timeout: timeout, idleTimeout: idleTimeout, maxRetries: maxRetries
            )
        }
    }

    /// The chat completions URL under `variable`, or under the default when it is unset or empty.
    /// Throws without echoing the value unless it is printable ASCII with no space, an http or https URL
    /// with a host that `isHost` accepts, a port from 1 to 65535 if it names one, and no user info, query or fragment.
    static func endpoint(_ variable: String?) throws -> URL {
        let invalid = InferenceError.invalidRequest(
            "MOSS_INFERENCE_URL must be an absolute http or https URL with a host and no user info, query or fragment"
        )
        let base = variable.flatMap { $0.isEmpty ? nil : $0 } ?? defaultBaseURL
        guard base.unicodeScalars.allSatisfy({ (0x21...0x7E).contains($0.value) }),
            var parts = URLComponents(string: base), let text = parts.string, let host = parts.rangeOfHost, isHost(text[host]),
            ["http", "https"].contains(parts.scheme?.lowercased()), parts.port.map({ (1...65_535).contains($0) }) ?? true,
            parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil
        else { throw invalid }
        if parts.percentEncodedPath.hasSuffix("/") { parts.percentEncodedPath.removeLast() }
        parts.percentEncodedPath += "/chat/completions"
        guard let url = parts.url else { throw invalid }
        return url
    }

    /// Whether `host`, as the URL writes it, is a name with no `%`, or an IPv6
    /// address in brackets whose zone, if any, is `%25` and then letters, digits or `-._~`.
    static func isHost(_ host: Substring) -> Bool {
        guard host.hasPrefix("["), host.hasSuffix("]") else { return !host.isEmpty && !host.contains("%") }
        let pieces = host.dropFirst().dropLast().components(separatedBy: "%25")
        let address = CharacterSet(charactersIn: "0123456789ABCDEFabcdef:.")
        let zone = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        return pieces.count <= 2 && !pieces[0].isEmpty && pieces[0].unicodeScalars.allSatisfy(address.contains)
            && pieces.dropFirst().allSatisfy { !$0.isEmpty && $0.unicodeScalars.allSatisfy(zone.contains) }
    }

    /// Throws unless `value` is a credential or key that is not empty and fits in a header.
    static func checkValue(_ name: String, _ value: String) throws {
        if value.isEmpty { throw InferenceError.invalidRequest("\(name) must not be empty") }
        try checkHeader(name, value)
    }

    /// Throws unless `value` is printable ASCII with no space at either end,
    /// since HTTP trims those spaces and a key made only of spaces would arrive empty.
    static func checkHeader(_ name: String, _ value: String) throws {
        if !value.unicodeScalars.allSatisfy({ (0x20...0x7E).contains($0.value) }) {
            throw InferenceError.invalidRequest("\(name) must be printable ASCII, with no newline or control character")
        }
        if value.first == " " || value.last == " " {
            throw InferenceError.invalidRequest("\(name) must not start or end with a space")
        }
    }

    /// `seconds` as a limit, `nil` for none, or an error when it is not above zero.
    static func limit(_ seconds: TimeInterval?, _ name: String) throws -> TimeInterval? {
        guard let seconds, seconds != .infinity else { return nil }
        guard seconds > 0 else { throw InferenceError.invalidRequest("\(name) must be above zero") }
        return seconds
    }

    /// `count` as a number of retries, or an error when it is below zero.
    static func retries(_ count: Int) throws -> Int {
        guard count >= 0 else { throw InferenceError.invalidRequest("maxRetries must not be below zero") }
        return count
    }
}

/// A streamed chat completion, an `AsyncSequence` of chunks to iterate once.
///
/// Leaving the loop early, cancelling the task or calling `cancel()` closes the connection,
/// and the gateway then stops the model. After `cancel()` the loop ends quietly, a cancelled
/// task throws `CancellationError`, and a passed limit throws `InferenceError` of type `timeout`.
/// Top-level code, such as main.swift or a playground, can keep the iterator alive past a `break`,
/// so call `cancel()` there after leaving the loop early, or the connection stays open until it ends.
///
/// A body still open 0.1 seconds after `[DONE]` is cut off, which closes its connection.
/// An event or a line over 1 MiB throws `InferenceError` of type `server_error` and closes the connection.
public final class ChatCompletionStream: AsyncSequence, @unchecked Sendable {
    public typealias Element = ChatCompletionChunk

    private let reader: EventReader

    init(reader: EventReader) { self.reader = reader }

    deinit { reader.close(unlessIterated: true) }

    public func makeAsyncIterator() -> AsyncIterator { AsyncIterator(reader) }

    /// The gateway's `X-Moss-Request-Id` for the call, or `nil` when the response has none.
    public var requestId: String? { reader.requestId }

    /// Closes the connection. A loop over the stream then ends without an error.
    public func cancel() { reader.cancel() }

    /// Closes the connection when the loop lets go of it before the stream ends.
    public final class AsyncIterator: AsyncIteratorProtocol {
        private let reader: EventReader

        init(_ reader: EventReader) {
            self.reader = reader
            reader.locked { reader.iterated = true }
        }

        deinit { reader.close(unlessIterated: false) }

        public func next() async throws -> ChatCompletionChunk? { try await reader.next() }
    }

    /// Sends `request`, again up to `maxRetries` times after a `Retryable` failure, and returns the stream.
    /// A wait that would pass `timeout` throws that failure at once instead, and cancelling the task ends a wait.
    /// Each wait is a `Retry-After` of 60 seconds or less, else 0.5 seconds doubled per retry, capped at 8, with up to 25 percent jitter.
    static func open(
        _ request: URLRequest, in session: URLSession, timeout: TimeInterval?, idleTimeout: TimeInterval?, maxRetries: Int
    ) async throws -> ChatCompletionStream {
        let start = DispatchTime.now()
        var retries = 0
        while true {
            do {
                return try await send(request, in: session, call: CallDelegate(timeout: timeout, idleTimeout: idleTimeout, start: start))
            } catch let failure as Retryable {
                let backoff = Swift.min(0.5 * pow(2, Double(retries)), 8) * .random(in: 0.75...1)
                let wait = failure.error.retryAfter.flatMap { $0 <= 60 ? $0 : nil } ?? backoff
                guard retries < maxRetries, timeout.map({ DispatchTime.now() + wait < start + $0 }) ?? true else { throw failure.error }
                try await Task.sleep(nanoseconds: UInt64(wait * 1e9))
                retries += 1
            }
        }
    }

    /// Sends `request` once and returns the stream when its response headers arrive.
    /// A failure to connect, or a connection lost before the headers, throws as `Retryable`.
    /// A non-2xx answer throws its status, unless a limit passes or the task is cancelled while its body is read,
    /// as `Retryable` for 408, 409, 429 or 500 and above unless `x-should-retry` is `false`, or for any when it is `true`.
    private static func send(_ request: URLRequest, in session: URLSession, call: CallDelegate) async throws -> ChatCompletionStream {
        let sending = Task { try await session.bytes(for: request, delegate: call) }
        call.onExpiry { sending.cancel() }
        let (bytes, response): (URLSession.AsyncBytes, URLResponse)
        do {
            (bytes, response) = try await withTaskCancellationHandler { try await sending.value } onCancel: { sending.cancel() }
        } catch {
            call.stop()
            let failure = call.failure(error, requestId: nil)
            if let failure = failure as? InferenceError, failure.type == "connection_error" || call.connectFailed {
                throw Retryable(error: failure)
            }
            throw failure
        }
        call.sent()
        call.onExpiry { bytes.task.cancel() }
        let http = response as? HTTPURLResponse
        guard let http, (200..<300).contains(http.statusCode) else {
            var body = Data()
            var failure: Error?
            do { for try await byte in bytes.prefix(65_536) { body.append(byte) } } catch {
                failure = call.failure(error, requestId: http?.requestId, retryAfter: http?.retryAfter)
            }
            bytes.task.cancel()
            call.stop()
            if let failure, failure is CancellationError || (failure as? InferenceError)?.type == "timeout" { throw failure }
            let status = http?.statusCode ?? 0
            let shouldRetry = http?.value(forHTTPHeaderField: "x-should-retry")
            let error = InferenceError(response: http, body: body)
            if shouldRetry == "true" || shouldRetry != "false" && ([408, 409, 429].contains(status) || status >= 500) {
                throw Retryable(error: error)
            }
            throw error
        }
        return ChatCompletionStream(reader: EventReader(bytes, call, http.requestId))
    }
}

/// A failed attempt that another attempt may follow.
private struct Retryable: Error {
    let error: InferenceError
}

/// Reads server-sent events from a response body and decodes each into a chunk.
final class EventReader: @unchecked Sendable {
    /// The most bytes one line, or the joined data of one event, may hold.
    static let maxEventSize = 1 << 20
    /// How long the body may stay open after `[DONE]` before the request is cancelled.
    /// A body that ends sooner keeps its connection for the next call while the stream is held.
    /// `create()` lets go of the stream at `[DONE]`, so a body that is still open then closes its connection.
    static let drainTime: TimeInterval = 0.1

    private var bytes: URLSession.AsyncBytes.Iterator
    private var skipLineFeed = false
    private let task: URLSessionDataTask
    private let call: CallDelegate
    /// The response's `X-Moss-Request-Id`, which every failure of the stream carries.
    let requestId: String?
    private let lock = NSLock()
    private var finished = false
    /// Whether a chunk has carried an MCP tool step, after which every failure has the code `failed_after_tool_call`.
    private var toolRan = false
    /// The tool calls of each choice so far, by choice index.
    private var slots: [Int: ToolSlots] = [:]
    var iterated = false

    init(_ bytes: URLSession.AsyncBytes, _ call: CallDelegate, _ requestId: String?) {
        self.bytes = bytes.makeAsyncIterator()
        task = bytes.task
        self.call = call
        self.requestId = requestId
    }

    func locked<T>(_ body: () -> T) -> T { lock.locked(body) }

    /// The next chunk, or `nil` after `[DONE]` or `cancel()`.
    func next() async throws -> ChatCompletionChunk? {
        if locked({ finished }) { return nil }
        do { return try await nextChunk() } catch {
            let cancelled = locked { finished }
            finish()
            task.cancel()
            if cancelled { return nil }
            let failure = error is InferenceError ? error : call.failure(error, requestId: requestId)
            guard toolRan, var stepped = failure as? InferenceError else { throw failure }
            stepped.code = "failed_after_tool_call"
            throw stepped
        }
    }

    private func nextChunk() async throws -> ChatCompletionChunk? {
        var data = ""
        while data.isEmpty {
            guard let event = try await nextEvent() else {
                throw failure("incomplete_stream", "The stream ended before [DONE]")
            }
            data = event
        }
        if data == "[DONE]" {
            finish()
            DispatchQueue.global().asyncAfter(deadline: .now() + Self.drainTime) { [task] in task.cancel() }
            return nil
        }
        guard let event = try? JSONDecoder().decode([String: JSONValue].self, from: Data(data.utf8)) else {
            throw failure("server_error", "The stream sent an event that is not JSON")
        }
        if let error = event["error"], error.object != nil {
            let type = error["type"]?.string ?? "model_error"
            throw failure(type, error["message"]?.string ?? "The stream failed", code: InferenceError.code(Data(data.utf8)))
        }
        let chunk = ChatCompletionChunk(event, slots: &slots)
        toolRan = toolRan || chunk.toolStep != nil
        return chunk
    }

    private func failure(_ type: String, _ message: String, code: String? = nil) -> InferenceError {
        InferenceError(status: nil, type: type, message: message, code: code, requestId: requestId)
    }

    private var tooLarge: InferenceError { failure("server_error", "The gateway sent an event over 1 MiB.") }

    /// The joined `data` lines of the next event,
    /// or `nil` when the body ends before its blank line.
    /// Throws once the joined data grows past `maxEventSize`.
    private func nextEvent() async throws -> String? {
        var data = ""
        var hasData = false
        while let line = try await nextLine() {
            if line.isEmpty, hasData { return data }
            let field = line.prefix { $0 != ":" }
            guard field == "data" else { continue }
            var value = line.dropFirst(field.count + 1)
            if value.hasPrefix(" ") { value = value.dropFirst() }
            if hasData { data.append("\n") }
            data.append(contentsOf: value)
            hasData = true
            if data.utf8.count > Self.maxEventSize { throw tooLarge }
        }
        return nil
    }

    /// The next line, ended by LF, CR or CRLF, or `nil` at the end of the body.
    /// Throws once a line still without its end grows past `maxEventSize` bytes.
    private func nextLine() async throws -> String? {
        var line: [UInt8] = []
        while let byte = try await bytes.next() {
            if skipLineFeed {
                skipLineFeed = false
                if byte == 0x0A { continue }
            }
            if byte == 0x0A || byte == 0x0D {
                skipLineFeed = byte == 0x0D
                return String(decoding: line, as: UTF8.self)
            }
            if line.count == Self.maxEventSize { throw tooLarge }
            line.append(byte)
        }
        return line.isEmpty ? nil : String(decoding: line, as: UTF8.self)
    }

    private func finish() {
        locked { finished = true }
        call.stop()
    }

    /// Cancels the request unless the stream has ended, or when asked, unless an iterator owns it.
    func close(unlessIterated: Bool) {
        if !locked({ finished || (unlessIterated && iterated) }) { cancel() }
    }

    /// Ends the stream and closes the connection.
    func cancel() {
        finish()
        task.cancel()
    }
}

/// The task delegate of one call. It refuses redirects and ends a call that runs past
/// the connect limit or the caller's timeout. URLSession has no connect timeout, so this hears
/// when the request body is sent, which means the connection is up, and lifts the connect limit.
final class CallDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private let idleTimeout: TimeInterval?
    private var timers: [DispatchWorkItem] = []
    private var cancelCall: (() -> Void)?
    private var requestSent = false
    /// The message of the limit that ended the call, and whether it was the connect limit.
    private var expiry: (message: String, connecting: Bool)?

    /// Starts the connect limit now and the `timeout` of a call that began at `start`.
    init(timeout: TimeInterval?, idleTimeout: TimeInterval?, start: DispatchTime) {
        self.idleTimeout = idleTimeout
        super.init()
        let connect = MossInference.connectTimeout
        schedule(.now() + connect, connecting: true, "Could not connect and send the request within \(connect) seconds")
        if let timeout { schedule(start + timeout, connecting: false, "The call did not finish within \(timeout) seconds") }
    }

    private func locked<T>(_ body: () -> T) -> T { lock.locked(body) }

    private func schedule(_ deadline: DispatchTime, connecting: Bool, _ message: String) {
        let timer = DispatchWorkItem { [weak self] in
            guard let self else { return }
            let cancel = self.locked { () -> (() -> Void)? in
                guard self.expiry == nil, !(connecting && self.requestSent) else { return nil }
                self.expiry = (message, connecting)
                return self.cancelCall
            }
            cancel?()
        }
        timers.append(timer)
        DispatchQueue.global().asyncAfter(deadline: deadline, execute: timer)
    }

    /// Sets what to cancel when a limit passes, and cancels it at once when one already has.
    func onExpiry(_ cancel: @escaping () -> Void) {
        if locked({ cancelCall = cancel; return expiry != nil }) { cancel() }
    }

    func sent() { locked { requestSent = true } }

    /// Whether the call failed before it sent its request, with `timeout` not yet passed.
    var connectFailed: Bool { locked { !requestSent && expiry?.connecting != false } }

    func stop() {
        locked {
            timers.forEach { $0.cancel() }
            cancelCall = nil
        }
    }

    func urlSession(
        _ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
        totalBytesSent: Int64, totalBytesExpectedToSend: Int64
    ) { sent() }

    /// Keeps the 3xx answer as the response, so the bearer never goes to another URL.
    func urlSession(
        _ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest
    ) async -> URLRequest? { nil }

    /// The error to throw for a transport failure before or during the stream,
    /// carrying the `requestId` and `retryAfter` of the response once it has arrived.
    func failure(_ error: Error, requestId: String?, retryAfter: TimeInterval? = nil) -> Error {
        let code = (error as? URLError)?.code
        let (type, message): (String, String)
        if let expiry = locked({ expiry }) {
            (type, message) = ("timeout", expiry.message)
        } else if error is CancellationError || code == .cancelled {
            return CancellationError()
        } else if code == .timedOut {
            (type, message) = ("timeout", idleTimeout.map { "The gateway sent no data for \($0) seconds" } ?? error.localizedDescription)
        } else {
            (type, message) = ("connection_error", error.localizedDescription)
        }
        return InferenceError(status: nil, type: type, message: message, requestId: requestId, retryAfter: retryAfter)
    }
}

extension NSLock {
    /// Runs `body` holding the lock, as `withLock` does from iOS 16.
    func locked<T>(_ body: () -> T) -> T {
        lock()
        defer { unlock() }
        return body()
    }
}
