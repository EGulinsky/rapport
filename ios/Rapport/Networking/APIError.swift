import Foundation

/// Mirrors frontend/src/api/client.ts's ApiError: the backend's error responses
/// carry `detail` as either a plain string (FastAPI's default validation errors)
/// or `{error_key, message}` (this app's stable error-key scheme, see
/// backend/app/error_keys.py). `errorKey` lets a view show a localized string
/// instead of the German fallback `message` when one is available.
struct APIError: Error, LocalizedError, Equatable {
    let message: String
    let errorKey: String?
    let statusCode: Int?

    var errorDescription: String? { message }

    static let notConfigured = APIError(message: "No server configured.", errorKey: nil, statusCode: nil)
    static let unauthorized = APIError(message: "Not signed in.", errorKey: nil, statusCode: 401)

    /// Parses a non-2xx response body, falling back to the raw body text
    /// (or the HTTP status) when it isn't the expected JSON shape.
    static func from(data: Data, statusCode: Int) -> APIError {
        struct DetailObject: Decodable {
            let error_key: String?
            let message: String?
        }
        struct Envelope: Decodable {
            let detail: AnyDetail
        }
        enum AnyDetail: Decodable {
            case string(String)
            case object(DetailObject)

            init(from decoder: Decoder) throws {
                let container = try decoder.singleValueContainer()
                if let s = try? container.decode(String.self) {
                    self = .string(s)
                } else {
                    self = .object(try container.decode(DetailObject.self))
                }
            }
        }

        if let envelope = try? JSONDecoder().decode(Envelope.self, from: data) {
            switch envelope.detail {
            case .string(let s):
                return APIError(message: s, errorKey: nil, statusCode: statusCode)
            case .object(let obj):
                return APIError(
                    message: obj.message ?? "\(statusCode)",
                    errorKey: obj.error_key,
                    statusCode: statusCode
                )
            }
        }

        let raw = String(data: data, encoding: .utf8) ?? ""
        return APIError(message: raw.isEmpty ? "\(statusCode)" : raw, errorKey: nil, statusCode: statusCode)
    }
}
