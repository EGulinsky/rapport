import Foundation

/// Mirrors backend/app/schemas.py's AttachmentRead.
struct Attachment: Codable, Identifiable, Equatable {
    let id: Int
    var filename: String
    var contentType: String?
    var sizeBytes: Int?
    var source: String?
    var createdAt: String?
}

/// Mirrors backend/app/schemas.py's EventRead — a single timeline entry
/// (mail, calendar, call, note, manual comment, status change, ...).
struct Event: Codable, Identifiable, Equatable {
    let id: Int
    var applicationId: Int
    var typ: String
    var datum: String?
    var titel: String?
    var notiz: String?
    var autor: String?
    var source: String?
    /// "sent" / "received" — mail events only, nil otherwise.
    var mailDirection: String?
    var externalId: String?
    /// Ready-to-use deep link when external_id alone can't be turned into a
    /// working URL client-side (currently only gcal — see models.py).
    var externalUrl: String?
    var datumZeit: String?
    /// True when datum_zeit is the v4.6.7 noon-backfill's placeholder rather
    /// than a real timestamp — hide the time instead of showing a fake one.
    var datumZeitIsPlaceholder: Bool?
    var createdAt: String?
    var attachments: [Attachment]

    enum EventType: String {
        case bewerbung, gespräch, notiz, status
    }
}

/// Mirrors backend/app/schemas.py's EventCreate — datum is date-only on
/// creation; setting a specific time on an existing event goes through
/// EventUpdatePayload instead (see backend's EventUpdate/EventBase split).
struct EventCreatePayload: Encodable {
    var applicationId: Int
    var typ: String
    var datum: String?
    var titel: String?
    var notiz: String?
    var autor: String?
    var source: String?
}

/// Mirrors backend/app/schemas.py's EventUpdate.
struct EventUpdatePayload: Encodable {
    var typ: String?
    var datum: String?
    /// Naive datetime string representing Europe/Berlin wall-clock time —
    /// the backend converts to naive UTC in update_event(). Send an explicit
    /// null to clear a previously-set time; omit the key to leave it as-is
    /// (Encodable naturally omits nil fields here since JSONEncoder skips
    /// them — there is currently no call site that needs the "explicit
    /// null" distinction from Swift, unlike the web form).
    var datumZeit: String?
    var titel: String?
    var notiz: String?
}
