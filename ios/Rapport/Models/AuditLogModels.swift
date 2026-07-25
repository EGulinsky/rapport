import Foundation

/// audit_log.py has no Pydantic response model at all (despite `AuditLog`
/// being a full ORM model) — every field here is hand-transcribed from the
/// router's dict-building code. `entityType`/`action`/`source` are free-text
/// DB columns, not enums, so they stay `String` rather than a closed Swift
/// enum (a future new value must not fail to decode).
struct AuditLogEntry: Decodable, Identifiable {
    var id: Int
    var appId: Int?
    var appFirma: String?
    var appRolle: String?
    var contactId: Int?
    var contactName: String?
    var companyProfileId: Int?
    var companyName: String?
    var eventId: Int?
    var eventTitel: String?
    var entityType: String?
    var timestamp: String?
    var action: String
    var field: String?
    var oldValue: String?
    var newValue: String?
    var source: String
    var reason: String?
}

struct AuditLogResponse: Decodable {
    var total: Int
    var items: [AuditLogEntry]
}

struct AuditLogDeleteResult: Decodable {
    var deleted: Int
}
