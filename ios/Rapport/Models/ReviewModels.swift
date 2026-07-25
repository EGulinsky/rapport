import Foundation

/// Mirrors review.py's `PendingMatchRead` — every field beyond
/// id/source/confidence is genuinely optional depending on match type.
struct PendingMatchRead: Decodable, Identifiable {
    var id: Int
    var source: String
    var confidence: Int
    var eventType: String?
    var datum: String?
    var titel: String?
    var extract: String?
    /// Free-text, sometimes itself JSON-encoded depending on `eventType`
    /// (e.g. duplicate_contact carries `{"keeper_contact_id":..,"dup_contact_id":..}`).
    /// Kept as a raw string rather than structurally decoded.
    var rawContent: String?
    var suggestedAppId: Int?
    var suggestedAppFirma: String?
    var suggestedAppRolle: String?
    var suggestedMainStatus: String?
    var suggestedSubStatus: String?
    var currentMainStatus: String?
    var statusOnly: Bool
    var createdAt: String?
}

struct ApproveMatchPayload: Encodable {
    var applicationId: Int?
    var eventType: String?
    var datum: String?
    var titel: String?
    var linkedinUrl: String?
}

struct ApproveMatchResult: Decodable {
    var status: String
    var eventId: Int?
}

struct RejectMatchResult: Decodable {
    var status: String
}

struct ReviewCountResult: Decodable {
    var count: Int
}
