import Foundation

/// A JSON value, for request and response fields the typed API does not model.
public enum JSONValue: Sendable, Hashable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    /// The member named `key` when this is an object.
    public subscript(key: String) -> JSONValue? {
        if case .object(let object) = self { return object[key] }
        return nil
    }

    var string: String? { if case .string(let value) = self { value } else { nil } }
    var array: [JSONValue]? { if case .array(let value) = self { value } else { nil } }
    var object: [String: JSONValue]? { if case .object(let value) = self { value } else { nil } }
    var int: Int? {
        if case .int(let value) = self { value } else if case .double(let value) = self { Int(exactly: value) } else { nil }
    }
}

extension JSONValue: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Int.self) { self = .int(value) }
        else if let value = try? container.decode(Double.self) { self = .double(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else { self = .object(try container.decode([String: JSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let value): try container.encode(value)
        case .int(let value): try container.encode(value)
        case .double(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        }
    }
}

extension JSONValue: ExpressibleByNilLiteral, ExpressibleByBooleanLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByFloatLiteral, ExpressibleByStringLiteral, ExpressibleByArrayLiteral,
    ExpressibleByDictionaryLiteral
{
    public init(nilLiteral: ()) { self = .null }
    public init(booleanLiteral value: Bool) { self = .bool(value) }
    public init(integerLiteral value: Int) { self = .int(value) }
    public init(floatLiteral value: Double) { self = .double(value) }
    public init(stringLiteral value: String) { self = .string(value) }
    public init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
    public init(dictionaryLiteral elements: (String, JSONValue)...) {
        self = .object(Dictionary(elements, uniquingKeysWith: { _, last in last }))
    }
}

/// One message of a chat completion request.
public enum ChatMessage: Sendable, Hashable {
    case system(String)
    case user(String)
    case assistant(String)
    /// Any other message as its JSON object, such as a tool result or an assistant turn with tool calls.
    case raw([String: JSONValue])

    var json: JSONValue {
        switch self {
        case .system(let content): return ["role": "system", "content": .string(content)]
        case .user(let content): return ["role": "user", "content": .string(content)]
        case .assistant(let content): return ["role": "assistant", "content": .string(content)]
        case .raw(let object): return .object(object)
        }
    }
}

/// A failed inference call.
///
/// `status` is the HTTP status, `nil` when the call failed before a response or mid-stream.
/// `type` is the gateway's error type, or else one of `authentication_error`, `permission_error`,
/// `not_found_error`, `rate_limit_error`, `invalid_request_error` for another 4xx or an argument refused,
/// `server_error` for a 3xx or 5xx, `model_error` for a stream error without a type, `connection_error` for
/// a transport failure, `timeout` for a passed limit, or `incomplete_stream` when the reply ends before `[DONE]`.
public struct InferenceError: LocalizedError, Sendable, Hashable {
    public let status: Int?
    public let type: String
    public let message: String
    /// The gateway's `error.code`, with an integer code as its decimal text.
    public let code: String?
    /// The gateway's `X-Moss-Request-Id` for the call, once a response has arrived.
    public let requestId: String?
    /// The seconds to wait before trying again, from the `Retry-After` header of an error response.
    public let retryAfter: TimeInterval?

    public var errorDescription: String? { message }

    init(status: Int?, type: String, message: String, code: String? = nil, requestId: String? = nil, retryAfter: TimeInterval? = nil) {
        self.status = status
        self.type = type
        self.message = message
        self.code = code
        self.requestId = requestId
        self.retryAfter = retryAfter
    }
}

extension InferenceError {
    /// Maps a response that is not 2xx, whose body is JSON in one of the gateway's shapes or anything else,
    /// which becomes the message with its whitespace collapsed and cut to 300 characters, unless it is empty.
    init(response: HTTPURLResponse?, body: Data) {
        let status = response?.statusCode ?? 0
        let json = try? JSONDecoder().decode(JSONValue.self, from: body)
        let error = json?["error"]
        let detail = json?["detail"].map { $0.string ?? String(decoding: (try? JSONEncoder().encode($0)) ?? Data(), as: UTF8.self) }
        let text = String(decoding: body, as: UTF8.self).split(whereSeparator: \.isWhitespace).joined(separator: " ")
        let statusLine = "HTTP \(status) \(HTTPURLResponse.localizedString(forStatusCode: status))"
        let fallback = json != nil || text.isEmpty ? statusLine : text.count > 300 ? String(text.prefix(297)) + "..." : text
        self.init(
            status: status,
            type: error?["type"]?.string ?? Self.type(forStatus: status),
            message: error?["message"]?.string ?? error?.string ?? detail ?? fallback,
            code: Self.code(body),
            requestId: response?.requestId,
            retryAfter: response?.retryAfter
        )
    }

    /// The `code` of the gateway error object in the JSON `body`: a string as it is,
    /// an integer as its decimal text, and `nil` for a fraction, an exponent, a boolean or anything else.
    static func code(_ body: Data) -> String? {
        let json = try? JSONSerialization.jsonObject(with: body)
        switch ((json as? [String: Any])?["error"] as? [String: Any])?["code"] {
        case let code as String: return code
        case let code as NSNumber where CFGetTypeID(code) != CFBooleanGetTypeID() && !CFNumberIsFloatType(code): return code.stringValue
        default: return nil
        }
    }

    /// A `Retry-After` value in delta-seconds, a non-negative integer, or `nil` for an HTTP-date or anything else.
    static func seconds(_ retryAfter: String) -> TimeInterval? {
        guard !retryAfter.isEmpty, retryAfter.allSatisfy({ ("0"..."9").contains($0) }) else { return nil }
        return TimeInterval(retryAfter)
    }

    static func type(forStatus status: Int) -> String {
        switch status {
        case 401: "authentication_error"
        case 403: "permission_error"
        case 404: "not_found_error"
        case 429: "rate_limit_error"
        case 400..<500: "invalid_request_error"
        default: "server_error"
        }
    }

    static func invalidRequest(_ message: String) -> InferenceError {
        InferenceError(status: nil, type: "invalid_request_error", message: message)
    }
}

extension HTTPURLResponse {
    /// The `X-Moss-Request-Id` header, or `nil` when it is missing or empty.
    var requestId: String? { value(forHTTPHeaderField: "X-Moss-Request-Id").flatMap { $0.isEmpty ? nil : $0 } }
    /// The `Retry-After` header in seconds, or `nil` unless it is delta-seconds.
    var retryAfter: TimeInterval? { value(forHTTPHeaderField: "Retry-After").flatMap(InferenceError.seconds) }
}

/// Token counts for one completion.
public struct CompletionUsage: Sendable, Hashable {
    public let promptTokens: Int
    public let completionTokens: Int
    public let totalTokens: Int

    init(_ json: JSONValue) {
        promptTokens = json["prompt_tokens"]?.int ?? 0
        completionTokens = json["completion_tokens"]?.int ?? 0
        totalTokens = json["total_tokens"]?.int ?? 0
    }
}

/// One streamed piece of a chat completion, with OpenAI's fields.
public struct ChatCompletionChunk: Sendable, Hashable {
    public let id: String
    public let object: String
    public let created: Int
    public let model: String
    public let choices: [Choice]
    /// Token counts, usually on a last chunk whose `choices` is empty.
    public let usage: CompletionUsage?
    /// The decoded event, with the fields the typed properties leave out.
    public let raw: [String: JSONValue]

    public struct Choice: Sendable, Hashable {
        public let index: Int
        public let delta: Delta
        public let finishReason: String?
    }

    public struct Delta: Sendable, Hashable {
        public let role: String?
        public let content: String?
        public let toolCalls: [ToolCall]?
    }

    /// A piece of a tool call. The pieces with one `index` make up one call.
    public struct ToolCall: Sendable, Hashable {
        public let index: Int
        public let id: String?
        public let type: String?
        public let function: Function?
    }

    public struct Function: Sendable, Hashable {
        public let name: String?
        public let arguments: String?
    }

    init(_ raw: [String: JSONValue]) {
        self.raw = raw
        id = raw["id"]?.string ?? ""
        object = raw["object"]?.string ?? "chat.completion.chunk"
        created = raw["created"]?.int ?? 0
        model = raw["model"]?.string ?? ""
        usage = raw["usage"]?.object.map { CompletionUsage(.object($0)) }
        choices = (raw["choices"]?.array ?? []).map { choice in
            let delta = choice["delta"]
            let toolCalls = delta?["tool_calls"]?.array?.map { call in
                ToolCall(
                    index: call["index"]?.int ?? 0, id: call["id"]?.string, type: call["type"]?.string,
                    function: call["function"].map { Function(name: $0["name"]?.string, arguments: $0["arguments"]?.string) }
                )
            }
            return Choice(
                index: choice["index"]?.int ?? 0,
                delta: Delta(role: delta?["role"]?.string, content: delta?["content"]?.string, toolCalls: toolCalls),
                finishReason: choice["finish_reason"]?.string
            )
        }
    }
}

/// A whole chat completion, gathered from the stream.
public struct ChatCompletion: Sendable, Hashable {
    public let id: String
    public let object: String
    public let created: Int
    public let model: String
    public let choices: [Choice]
    public let usage: CompletionUsage?

    public struct Choice: Sendable, Hashable {
        public let index: Int
        public let message: Message
        public let finishReason: String?
    }

    public struct Message: Sendable, Hashable {
        public let role: String
        /// All text of the reply, `nil` when no text came.
        public let content: String?
        /// The tool calls with their arguments joined, `nil` when there are none.
        public let toolCalls: [ToolCall]?
    }

    public struct ToolCall: Sendable, Hashable {
        public let id: String
        public let type: String
        public let function: Function
    }

    public struct Function: Sendable, Hashable {
        public let name: String
        public let arguments: String
    }

    /// Reads `stream` to its end and joins its chunks by choice and tool call index.
    init(gathering stream: ChatCompletionStream, model: String) async throws {
        var first: ChatCompletionChunk?
        var usage: CompletionUsage?
        var builders: [Int: ChoiceBuilder] = [:]
        for try await chunk in stream {
            first = first ?? chunk
            usage = chunk.usage ?? usage
            for choice in chunk.choices {
                builders[choice.index, default: ChoiceBuilder()].add(choice)
            }
        }
        id = first?.id ?? ""
        object = "chat.completion"
        created = first?.created ?? 0
        self.model = first?.model ?? model
        choices = builders.keys.sorted().map { builders[$0]!.choice(index: $0) }
        self.usage = usage
    }
}

/// Joins the deltas of one choice.
private struct ChoiceBuilder {
    var role: String?
    var content: String?
    var finishReason: String?
    var calls: [Int: (id: String, type: String, name: String, arguments: String)] = [:]

    mutating func add(_ choice: ChatCompletionChunk.Choice) {
        role = choice.delta.role ?? role
        if let text = choice.delta.content, !text.isEmpty { content = (content ?? "") + text }
        finishReason = choice.finishReason ?? finishReason
        for piece in choice.delta.toolCalls ?? [] {
            var call = calls[piece.index] ?? (id: "", type: "function", name: "", arguments: "")
            if let id = piece.id, !id.isEmpty { call.id = id }
            if let type = piece.type, !type.isEmpty { call.type = type }
            if let name = piece.function?.name, !name.isEmpty { call.name = name }
            call.arguments += piece.function?.arguments ?? ""
            calls[piece.index] = call
        }
    }

    func choice(index: Int) -> ChatCompletion.Choice {
        let toolCalls = calls.sorted { $0.key < $1.key }.map { _, call in
            ChatCompletion.ToolCall(id: call.id, type: call.type, function: .init(name: call.name, arguments: call.arguments))
        }
        let message = ChatCompletion.Message(role: role ?? "assistant", content: content, toolCalls: toolCalls.isEmpty ? nil : toolCalls)
        return ChatCompletion.Choice(index: index, message: message, finishReason: finishReason)
    }
}
