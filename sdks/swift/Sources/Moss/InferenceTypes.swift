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
    var double: Double? {
        if case .double(let value) = self { value } else if case .int(let value) = self { Double(value) } else { nil }
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
    /// The result of the tool call whose id is `callId`.
    case tool(callId: String, content: String)
    /// Any other message as its JSON object.
    case raw([String: JSONValue])

    /// A reply to send back, with every field of its tool calls.
    public init(_ message: ChatCompletion.Message) { self = .raw(message.raw) }

    var json: JSONValue {
        switch self {
        case .system(let content): return ["role": "system", "content": .string(content)]
        case .user(let content): return ["role": "user", "content": .string(content)]
        case .assistant(let content): return ["role": "assistant", "content": .string(content)]
        case .tool(let callId, let content): return ["role": "tool", "tool_call_id": .string(callId), "content": .string(content)]
        case .raw(let object): return .object(object)
        }
    }
}

/// A tool the model may use: a function you run, an MCP server the gateway calls, or any other entry as JSON.
public enum Tool: Sendable, Hashable {
    /// A function you run. `parameters` is its JSON Schema, and `strict` asks the model to follow it exactly.
    case function(name: String, description: String? = nil, parameters: [String: JSONValue]? = nil, strict: Bool? = nil)
    /// An MCP server whose tools the gateway calls.
    case mcp(McpServer)
    /// Any other `tools` entry, sent and printed as it is, so MCP credentials belong in `.mcp(server)`.
    case raw([String: JSONValue])

    var json: JSONValue {
        switch self {
        case .function(let name, let description, let parameters, let strict):
            var function: [String: JSONValue] = ["name": .string(name)]
            function["description"] = description.map(JSONValue.string)
            function["parameters"] = parameters.map(JSONValue.object)
            function["strict"] = strict.map(JSONValue.bool)
            return ["type": "function", "function": .object(function)]
        case .mcp(let server): return server.json
        case .raw(let object): return .object(object)
        }
    }
}

/// Whether and how the model calls tools.
public enum ToolChoice: Sendable, Hashable {
    /// `auto` lets the model choose, `never` forbids a tool call and sends `none`, and `required` needs at least one.
    case auto, never, required
    /// The function with this name, which the model must call.
    case function(String)
    /// Any other `tool_choice` object, sent as it is.
    case raw([String: JSONValue])

    /// Spelled `.never`, since `.none` on a `ToolChoice?` is `nil` and sends no `tool_choice`.
    @available(*, unavailable, renamed: "never")
    public static var none: ToolChoice { .never }

    var json: JSONValue {
        switch self {
        case .auto: "auto"
        case .never: "none"
        case .required: "required"
        case .function(let name): ["type": "function", "function": ["name": .string(name)]]
        case .raw(let object): .object(object)
        }
    }
}

/// An MCP server the gateway calls, given in `tools` as `.mcp(server)`.
/// Its URL and `headers` can hold your credentials, so `description`, `debugDescription`
/// and `dump` show only the label and how many headers there are, never their names or values.
public struct McpServer: Sendable, Hashable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    /// How the gateway talks to the server.
    public enum Transport: String, Sendable, Hashable {
        case streamableHTTP = "streamable_http", sse
    }

    /// The server's name, which its tool steps carry.
    public let serverLabel: String
    /// The URL the gateway reaches the server at.
    public let serverURL: String
    /// Headers the gateway sends to the server, such as `Authorization`.
    public let headers: [String: String]?
    /// The server's tools the model may call, or all of them when `nil`.
    public let allowedTools: [String]?
    /// `streamableHTTP`, the gateway's default, or `sse`.
    public let transport: Transport?

    /// Holds the fields as given.
    public init(
        serverLabel: String, serverURL: String, headers: [String: String]? = nil, allowedTools: [String]? = nil, transport: Transport? = nil
    ) {
        self.serverLabel = serverLabel
        self.serverURL = serverURL
        self.headers = headers
        self.allowedTools = allowedTools
        self.transport = transport
    }

    /// The label and how many headers there are.
    public var description: String { "McpServer(serverLabel: \(serverLabel), headers: \(headers?.count ?? 0))" }
    /// The same as `description`.
    public var debugDescription: String { description }
    /// The label and how many headers there are, for `dump`.
    public var customMirror: Mirror { Mirror(self, children: ["serverLabel": serverLabel, "headers": headers?.count ?? 0]) }

    var json: JSONValue {
        var object: [String: JSONValue] = ["type": "mcp", "server_label": .string(serverLabel), "server_url": .string(serverURL)]
        object["headers"] = headers.map { .object($0.mapValues(JSONValue.string)) }
        object["allowed_tools"] = allowedTools.map { .array($0.map(JSONValue.string)) }
        object["transport"] = transport.map { .string($0.rawValue) }
        return .object(object)
    }
}

/// A failed inference call.
///
/// `status` is the HTTP status, `nil` when the call failed before a response or mid-stream.
/// `type` is the gateway's error type, such as `capacity` or `mcp_error`, or else one of `authentication_error`,
/// `permission_error`, `not_found_error`, `rate_limit_error`, `invalid_request_error` for another 4xx or an argument
/// refused, `server_error` for a 3xx or 5xx, `model_error` for a stream error without a type, `connection_error` for
/// a transport failure, `timeout` for a passed limit, or `incomplete_stream` when the reply ends before `[DONE]`.
public struct InferenceError: LocalizedError, Sendable, Hashable {
    public let status: Int?
    public let type: String
    public let message: String
    /// The gateway's `error.code`, with an integer code as its decimal text, or `failed_after_tool_call`
    /// for any failure once an MCP tool step has arrived, since a tool may have changed data and the call should not be replayed.
    public internal(set) var code: String?
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
    /// The usage object as the gateway sent it, with every field.
    public let raw: [String: JSONValue]
    public var promptTokens: Int { raw["prompt_tokens"]?.int ?? 0 }
    public var completionTokens: Int { raw["completion_tokens"]?.int ?? 0 }
    public var totalTokens: Int { raw["total_tokens"]?.int ?? 0 }
    /// The completion tokens by kind, when the gateway counts them.
    public var completionTokensDetails: CompletionTokensDetails? { raw["completion_tokens_details"]?.object.map(CompletionTokensDetails.init) }
    /// The prompt tokens by kind, when the gateway counts them.
    public var promptTokensDetails: PromptTokensDetails? { raw["prompt_tokens_details"]?.object.map(PromptTokensDetails.init) }
}

/// The completion tokens by kind, as in OpenAI's `CompletionTokensDetails`.
public struct CompletionTokensDetails: Sendable, Hashable {
    /// Tokens of a predicted output that the completion used.
    public let acceptedPredictionTokens: Int?
    /// Audio tokens the model made.
    public let audioTokens: Int?
    /// Tokens the model spent reasoning.
    public let reasoningTokens: Int?
    /// Tokens of a predicted output that the completion left out.
    public let rejectedPredictionTokens: Int?

    init(_ json: [String: JSONValue]) {
        acceptedPredictionTokens = json["accepted_prediction_tokens"]?.int
        audioTokens = json["audio_tokens"]?.int
        reasoningTokens = json["reasoning_tokens"]?.int
        rejectedPredictionTokens = json["rejected_prediction_tokens"]?.int
    }
}

/// The prompt tokens by kind, as in OpenAI's `PromptTokensDetails`.
public struct PromptTokensDetails: Sendable, Hashable {
    /// Audio tokens in the prompt.
    public let audioTokens: Int?
    /// Prompt tokens the provider read from its cache.
    public let cachedTokens: Int?

    init(_ json: [String: JSONValue]) {
        audioTokens = json["audio_tokens"]?.int
        cachedTokens = json["cached_tokens"]?.int
    }
}

/// The log probabilities of a choice's tokens, as in OpenAI's `ChoiceLogprobs`.
public struct ChoiceLogprobs: Sendable, Hashable {
    /// The content tokens, `nil` when none came.
    public let content: [ChatCompletionTokenLogprob]?
    /// The refusal tokens, `nil` when none came.
    public let refusal: [ChatCompletionTokenLogprob]?
}

extension ChoiceLogprobs {
    init(_ json: [String: JSONValue]) {
        self.init(
            content: json["content"]?.array?.map(ChatCompletionTokenLogprob.init),
            refusal: json["refusal"]?.array?.map(ChatCompletionTokenLogprob.init)
        )
    }

    /// These tokens followed by those of `next`, for each key.
    func appending(_ next: ChoiceLogprobs) -> ChoiceLogprobs {
        ChoiceLogprobs(
            content: next.content.map { (content ?? []) + $0 } ?? content, refusal: next.refusal.map { (refusal ?? []) + $0 } ?? refusal
        )
    }
}

/// One token and how likely it was, as in OpenAI's `ChatCompletionTokenLogprob`.
public struct ChatCompletionTokenLogprob: Sendable, Hashable {
    /// The token's text.
    public let token: String?
    /// The token's log probability.
    public let logprob: Double?
    /// The token's UTF-8 bytes.
    public let bytes: [Int]?
    /// The most likely tokens at this place, each with no `topLogprobs` of its own.
    public let topLogprobs: [ChatCompletionTokenLogprob]?

    init(_ json: JSONValue) {
        token = json["token"]?.string
        logprob = json["logprob"]?.double
        bytes = json["bytes"]?.array?.compactMap(\.int)
        topLogprobs = json["top_logprobs"]?.array?.map(Self.init)
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
    /// The MCP tool step this chunk carries, whose one choice has an empty delta, or `nil` on every other chunk.
    public let toolStep: ToolStep?
    /// The decoded event, with the fields the typed properties leave out.
    public let raw: [String: JSONValue]

    public struct Choice: Sendable, Hashable {
        public let index: Int
        public let delta: Delta
        public let finishReason: String?
        /// The log probabilities of this chunk's tokens, when `extra` asks for `logprobs`.
        public let logprobs: ChoiceLogprobs?
    }

    public struct Delta: Sendable, Hashable {
        public let role: String?
        public let content: String?
        public let toolCalls: [ToolCall]?
    }

    /// A piece of a tool call. The pieces with one `index` make up one call.
    public struct ToolCall: Sendable, Hashable {
        /// The piece's `index`. A piece without one takes the index of the call that has its `id`,
        /// else of its choice's last piece if the piece or that piece's call has no id, else the next free index.
        public let index: Int
        public let id: String?
        public let type: String?
        public let function: Function?
        /// The piece as the model sent it, with fields beyond OpenAI's such as Gemini's `extra_content`.
        public let raw: [String: JSONValue]
    }

    public struct Function: Sendable, Hashable {
        public let name: String?
        public let arguments: String?
    }

    /// Reads one event, with the tool call pieces of each choice placed after those `slots` has seen.
    init(_ raw: [String: JSONValue], slots: inout [Int: ToolSlots]) {
        self.raw = raw
        id = raw["id"]?.string ?? ""
        object = raw["object"]?.string ?? "chat.completion.chunk"
        created = raw["created"]?.int ?? 0
        model = raw["model"]?.string ?? ""
        usage = raw["usage"]?.object.map(CompletionUsage.init(raw:))
        toolStep = raw["moss_tool_step"]?.object.map(ToolStep.init(raw:))
        choices = (raw["choices"]?.array ?? []).map { choice in
            let index = choice["index"]?.int ?? 0
            let delta = choice["delta"]
            let toolCalls = delta?["tool_calls"]?.array?.compactMap { call -> ToolCall? in
                guard let object = call.object else { return nil }
                return ToolCall(
                    index: slots[index, default: ToolSlots()].place(index: call["index"]?.int, id: call["id"]?.string),
                    id: call["id"]?.string, type: call["type"]?.string,
                    function: call["function"].map { Function(name: $0["name"]?.string, arguments: $0["arguments"]?.string) },
                    raw: object
                )
            }
            return Choice(
                index: index,
                delta: Delta(role: delta?["role"]?.string, content: delta?["content"]?.string, toolCalls: toolCalls),
                finishReason: choice["finish_reason"]?.string, logprobs: choice["logprobs"]?.object.map(ChoiceLogprobs.init)
            )
        }
    }
}

/// The tool calls of one choice so far, which place each new piece in its call.
struct ToolSlots {
    /// The id of the call in each slot, empty while it has none.
    private var ids: [Int: String] = [:]
    /// The slot of the last piece.
    private var last: Int?

    /// Places a piece and returns its slot: its `index`, else the first slot whose call has its `id`,
    /// else the last piece's slot if the piece or that slot's call has no id, else the next free slot.
    mutating func place(index: Int?, id: String?) -> Int {
        let id = id ?? ""
        let named = id.isEmpty ? nil : ids.filter { $0.value == id }.keys.min()
        let slot = index ?? named ?? last.flatMap { id.isEmpty || ids[$0] == "" ? $0 : nil } ?? (ids.keys.max() ?? -1) + 1
        if !id.isEmpty || ids[slot] == nil { ids[slot] = id }
        last = slot
        return slot
    }
}

/// One step of an MCP tool call the gateway runs: `call` before the tool runs, `result` after.
public struct ToolStep: Sendable, Hashable {
    /// The step as the gateway sent it, with any field the typed properties leave out.
    public let raw: [String: JSONValue]
    /// `call` or `result`.
    public var type: String { raw["type"]?.string ?? "" }
    /// The id that a call and its result share.
    public var id: String { raw["id"]?.string ?? "" }
    /// The label of the MCP server whose tool ran.
    public var serverLabel: String { raw["server_label"]?.string ?? "" }
    /// The tool's name on its server.
    public var name: String { raw["name"]?.string ?? "" }
    /// The tool's arguments as JSON text, on a `call` step.
    public var arguments: String? { raw["arguments"]?.string }
    /// Whether the tool failed, on a `result` step.
    public var isError: Bool? { if case .bool(let value)? = raw["is_error"] { value } else { nil } }
    /// How long the tool ran in milliseconds, on a `result` step.
    public var durationMs: Double? { raw["duration_ms"]?.double }
    /// The tool's output, on a `result` step.
    public var output: String? { raw["output"]?.string }
}

/// A whole chat completion, gathered from the stream.
public struct ChatCompletion: Sendable, Hashable {
    public let id: String
    public let object: String
    public let created: Int
    public let model: String
    public let choices: [Choice]
    public let usage: CompletionUsage?
    /// The MCP tool steps of the turn in the order they arrived, empty when no tool ran.
    public let toolSteps: [ToolStep]
    /// The gateway's `X-Moss-Request-Id` for the call, or `nil` when the response has none.
    public let requestId: String?

    public struct Choice: Sendable, Hashable {
        public let index: Int
        public let message: Message
        public let finishReason: String?
        /// The tokens of every chunk joined in order, `nil` when no chunk had any.
        public let logprobs: ChoiceLogprobs?
    }

    public struct Message: Sendable, Hashable {
        public let role: String
        /// All text of the reply. When no text came, `nil` if there are tool calls and empty if not.
        public let content: String?
        /// The tool calls with their arguments joined, `nil` when there are none.
        public let toolCalls: [ToolCall]?

        /// The message as JSON, with every field of each tool call, which `ChatMessage(message)` sends back.
        public var raw: [String: JSONValue] {
            var raw: [String: JSONValue] = ["role": .string(role), "content": content.map(JSONValue.string) ?? .null]
            raw["tool_calls"] = toolCalls.map { .array($0.map { .object($0.raw) }) }
            return raw
        }
    }

    /// A tool call joined from its pieces.
    public struct ToolCall: Sendable, Hashable {
        /// The joined call, with every field the model sent such as Gemini's `extra_content`.
        public let raw: [String: JSONValue]
        public var id: String { raw["id"]?.string ?? "" }
        public var type: String { raw["type"]?.string ?? "function" }
        public var function: Function {
            Function(name: raw["function"]?["name"]?.string ?? "", arguments: raw["function"]?["arguments"]?.string ?? "")
        }
    }

    public struct Function: Sendable, Hashable {
        public let name: String
        public let arguments: String
    }

    /// Reads `stream` to its end and joins its chunks by choice and tool call index.
    init(gathering stream: ChatCompletionStream, model: String) async throws {
        var first: ChatCompletionChunk?
        var usage: CompletionUsage?
        var steps: [ToolStep] = []
        var builders: [Int: ChoiceBuilder] = [:]
        for try await chunk in stream {
            first = first ?? chunk
            usage = chunk.usage ?? usage
            if let step = chunk.toolStep { steps.append(step) }
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
        toolSteps = steps
        requestId = stream.requestId
    }
}

/// Joins the deltas of one choice.
private struct ChoiceBuilder {
    var role: String?
    var content: String?
    var finishReason: String?
    var logprobs: ChoiceLogprobs?
    var calls: [Int: [String: JSONValue]] = [:]

    /// Folds each tool call piece into the call of its `index` the way the gateway does, keeping every field.
    mutating func add(_ choice: ChatCompletionChunk.Choice) {
        role = choice.delta.role ?? role
        if let text = choice.delta.content, !text.isEmpty { content = (content ?? "") + text }
        finishReason = choice.finishReason ?? finishReason
        if let next = choice.logprobs { logprobs = logprobs?.appending(next) ?? next }
        for piece in choice.delta.toolCalls ?? [] {
            let slot = piece.index
            var call = calls[slot] ?? ["id": "", "type": "function", "function": ["name": "", "arguments": ""]]
            var function = call["function"]?.object ?? [:]
            if let id = piece.id, !id.isEmpty { call["id"] = .string(id) }
            if let type = piece.type, !type.isEmpty { call["type"] = .string(type) }
            if let name = piece.function?.name, !name.isEmpty { function["name"] = .string(name) }
            if let arguments = piece.function?.arguments { function["arguments"] = .string((function["arguments"]?.string ?? "") + arguments) }
            call["function"] = .object(function)
            for (key, value) in piece.raw where !["index", "id", "type", "function"].contains(key) && value != .null {
                if case .object(let new) = value, case .object(let old)? = call[key] {
                    call[key] = .object(old.merging(new) { $1 })
                } else {
                    call[key] = value
                }
            }
            calls[slot] = call
        }
    }

    func choice(index: Int) -> ChatCompletion.Choice {
        let toolCalls = calls.sorted { $0.key < $1.key }.map { ChatCompletion.ToolCall(raw: $0.value) }
        let message = ChatCompletion.Message(
            role: role ?? "assistant", content: content ?? (toolCalls.isEmpty ? "" : nil), toolCalls: toolCalls.isEmpty ? nil : toolCalls
        )
        return ChatCompletion.Choice(index: index, message: message, finishReason: finishReason, logprobs: logprobs)
    }
}
