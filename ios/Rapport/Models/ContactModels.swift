import Foundation

/// Mirrors backend/app/schemas.py's ContactPhoneOut / frontend's ContactPhone.
struct ContactPhone: Codable, Identifiable, Equatable {
    let id: Int
    var number: String
    var type: String
}

/// A phone entry not yet persisted (no id) — used when creating/editing a contact.
struct ContactPhoneInput: Codable, Equatable {
    var number: String
    var type: String = "other"
}

/// Mirrors backend/app/schemas.py's ContactRead / frontend's Contact.
struct Contact: Codable, Identifiable, Equatable {
    let id: Int
    var name: String
    var vorname: String?
    var email: String?
    var phones: [ContactPhone]
    var linkedinUrl: String?
    var firma: String?
    var rolle: String?
    var typ: String?
    var notizen: String?
    var letzterKontakt: String?
    var icloudLastSyncedAt: String?
    var createdAt: String?
    // Present on ContactWithApp (GET /api/contacts/ list) but not on the
    // ContactRead embedded in ApplicationRead.contacts — optional either way.
    var applications: [ApplicationBrief]?
    var companyWebsite: String?
    var companyProfileId: Int?

    /// Matches Contact.display_name (backend models.py) / the frontend's
    /// display-name convention: prefer "Vorname Nachname", fall back to the
    /// bare name field for contacts with no structured vorname/nachname split.
    var displayName: String {
        if let vorname, !vorname.trimmingCharacters(in: .whitespaces).isEmpty {
            return "\(vorname) \(name)"
        }
        return name
    }
}

/// Mirrors backend/app/schemas.py's ContactCreate.
struct ContactCreatePayload: Encodable {
    var name: String
    var vorname: String?
    var email: String
    var phones: [ContactPhoneInput] = []
    var linkedinUrl: String?
    var firma: String?
    var rolle: String?
    var typ: String?
    var notizen: String?
    var applicationId: Int?
}

/// Mirrors backend/app/schemas.py's ContactUpdate — every field optional so a
/// partial PATCH only touches what's set (all other fields nil = "no change").
struct ContactUpdatePayload: Encodable {
    var name: String?
    var vorname: String?
    var email: String?
    var phones: [ContactPhoneInput]?
    var linkedinUrl: String?
    var firma: String?
    var rolle: String?
    var typ: String?
    var notizen: String?
}

/// Mirrors contacts.py's ContactEventItem — one row in a contact's
/// calls/mails/messages/calendar event lists (GET /api/contacts/{id}/events).
struct ContactEventItem: Codable, Identifiable, Equatable {
    let id: Int
    var applicationId: Int
    var companyName: String?
    var rolle: String?
    var typ: String
    var datum: String?
    var titel: String?
    var notiz: String?
    var source: String?
    var externalId: String?
    var externalUrl: String?
    var createdAt: String?
}

/// Mirrors contacts.py's response shape for GET /api/contacts/{id}/events.
struct ContactEvents: Codable, Equatable {
    var calls: [ContactEventItem]
    var mails: [ContactEventItem]
    var messages: [ContactEventItem]
    var calendar: [ContactEventItem]
}
