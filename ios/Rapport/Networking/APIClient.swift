import Foundation

/// Thin async/await HTTP client mirroring frontend/src/api/client.ts's `request()` +
/// `authFetch()`: every call is relative to `/api` on the configured server, carries
/// `Authorization: Bearer <token>` when a token is set, and throws `APIError` on any
/// non-2xx response. Posts `.rapportUnauthorized` on a 401 so `SessionStore` can react
/// (clear the token, drop back to the login screen) without every call site handling it.
actor APIClient {
    static let apiPathPrefix = "/api"

    private let session: URLSession
    private var baseURL: URL?
    private var token: String?

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    init(session: URLSession = .shared) {
        self.session = session
    }

    func updateBaseURL(_ url: URL?) {
        baseURL = url
    }

    func updateToken(_ token: String?) {
        self.token = token
    }

    enum HTTPMethod: String {
        case get = "GET"
        case post = "POST"
        case patch = "PATCH"
        case put = "PUT"
        case delete = "DELETE"
    }

    /// - Parameters:
    ///   - path: e.g. "/applications/" — joined onto `{baseURL}/api`.
    ///   - query: appended as `?key=value` pairs, matching URLSearchParams usage on the web side.
    func request<Response: Decodable>(
        _ path: String,
        method: HTTPMethod = .get,
        query: [String: String?] = [:],
        body: Encodable? = nil
    ) async throws -> Response {
        let data = try await rawRequest(path, method: method, query: query, body: body)
        do {
            return try Self.decoder.decode(Response.self, from: data)
        } catch {
            throw APIError(message: "Decoding failed: \(error)", errorKey: nil, statusCode: nil)
        }
    }

    /// For endpoints with no meaningful response body (e.g. 204 No Content).
    @discardableResult
    func requestVoid(
        _ path: String,
        method: HTTPMethod = .get,
        query: [String: String?] = [:],
        body: Encodable? = nil
    ) async throws -> Data {
        try await rawRequest(path, method: method, query: query, body: body)
    }

    private func rawRequest(
        _ path: String,
        method: HTTPMethod,
        query: [String: String?],
        body: Encodable?
    ) async throws -> Data {
        guard let baseURL else { throw APIError.notConfigured }
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(Self.apiPathPrefix).appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        ) else {
            throw APIError(message: "Invalid URL for \(path)", errorKey: nil, statusCode: nil)
        }

        let nonNilQuery = query.compactMapValues { $0 }
        if !nonNilQuery.isEmpty {
            components.queryItems = nonNilQuery.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        guard let url = components.url else {
            throw APIError(message: "Invalid URL for \(path)", errorKey: nil, statusCode: nil)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.httpBody = try Self.encoder.encode(AnyEncodable(body))
        }

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(message: "No HTTP response", errorKey: nil, statusCode: nil)
        }

        if http.statusCode == 401 {
            await MainActor.run {
                NotificationCenter.default.post(name: .rapportUnauthorized, object: nil)
            }
        }

        guard (200...299).contains(http.statusCode) else {
            throw APIError.from(data: data, statusCode: http.statusCode)
        }

        return data
    }
}

extension Notification.Name {
    static let rapportUnauthorized = Notification.Name("rapport.unauthorized")
}

/// Type-erasing wrapper so `Encodable` values (which aren't themselves an
/// existential-friendly protocol for encoding) can be passed as `any Encodable`.
private struct AnyEncodable: Encodable {
    private let value: Encodable
    init(_ value: Encodable) { self.value = value }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}
