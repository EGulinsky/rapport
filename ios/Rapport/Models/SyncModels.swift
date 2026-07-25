import Foundation

/// Shared progress entry, one per sync source, keyed by source name
/// ("gmail", "gcal", "icloud_mail", "targeted_42", ...). Despite living
/// behind the `/api/sync/google/progress` path, this dict is populated by
/// every sync source in the app (sync_common.py's module-level singleton) —
/// poll this one endpoint for all of them, not a per-source endpoint.
struct ProgressEntry: Decodable {
    var label: String
    var step: String
    var current: Int
    var total: Int
    var percent: Int
    var done: Bool
    var created: Int
    var updated: Int
    var skipped: Int
}

/// A `batch/results[source]` entry. Genuinely untyped on the backend (each
/// source's background task dumps whatever dict it wants) — every field
/// beyond `done` is optional so an unexpected shape doesn't crash the decode.
struct BatchResult: Decodable {
    var done: Bool
    var processed: Int?
    var created: Int?
    var updated: Int?
    var skipped: Int?
    var errors: [String]?
}

/// The immediate response most `POST /api/sync/.../{source}` trigger
/// endpoints return. For nearly all sources this is a stub
/// (processed=0, created=0, skipped=0) — the real result lands later in
/// `batch/results[source]`. Exceptions that return the real result
/// synchronously: `POST /sync/icloud/contacts`, `.../notes/verify-2fa`,
/// `.../notes/_legacy`.
struct SyncResult: Decodable {
    var processed: Int
    var created: Int
    var skipped: Int
    var updated: Int = 0
    var errors: [String] = []
    var requiresTwoFa: Bool = false

    enum CodingKeys: String, CodingKey {
        case processed, created, skipped, updated, errors
        // JSONDecoder's .convertFromSnakeCase strategy transforms the raw
        // JSON key BEFORE matching it against CodingKeys — so this has to
        // be the already-transformed form, not "requires_2fa" as written on
        // the wire. Verified empirically (a naive "requires_2fa" raw value
        // silently fails to match and the field decodes as its default):
        // "requires_2fa" -> "requires2Fa" (capital F — the algorithm
        // capitalizes the token after a digit same as any other word
        // boundary).
        case requiresTwoFa = "requires2Fa"
    }

    // Several sources (gmail, icloud_mail, icloud_notes, icloud_reminders,
    // local_files) never send "updated" at all — Swift's synthesized
    // Decodable does NOT fall back to a property's default value for a
    // missing key (that default only applies to the memberwise init), so a
    // plain `= 0` default alone would still throw keyNotFound. Hand-roll
    // the decode to actually apply the defaults.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        processed = try container.decode(Int.self, forKey: .processed)
        created = try container.decode(Int.self, forKey: .created)
        skipped = try container.decode(Int.self, forKey: .skipped)
        updated = try container.decodeIfPresent(Int.self, forKey: .updated) ?? 0
        errors = try container.decodeIfPresent([String].self, forKey: .errors) ?? []
        requiresTwoFa = try container.decodeIfPresent(Bool.self, forKey: .requiresTwoFa) ?? false
    }
}

struct GoogleSyncStatus: Decodable {
    var connected: Bool
    var clientId: String?
    var gmailLastSync: String?
    var gcalLastSync: String?
}

struct GoogleCredentialsPayload: Encodable {
    var clientId: String
    var clientSecret: String
}

struct ICloudSyncStatus: Decodable {
    var connected: Bool
    var appleId: String?
    var icloudEmail: String?
    var mailLastSync: String?
    var calendarLastSync: String?
    var remindersLastSync: String?
    var contactsLastSync: String?
    var notesLastSync: String?
}

struct ICloudCredentialsPayload: Encodable {
    var appleId: String
    var appPassword: String
    var icloudEmail: String?
    var webPassword: String?
}

/// `{"code": "..."}` on the wire. Kept as two distinct Swift types even
/// though the backend reuses one Pydantic model for both, since one call
/// site carries a real 2FA code and the other a plain Apple ID password —
/// collapsing them risks a future refactor breaking the wrong one silently.
struct TwoFACodePayload: Encodable {
    var code: String
}

struct ICloudWebPasswordPayload: Encodable {
    var code: String
}

struct CallsStatus: Decodable {
    var enabled: Bool
    var lastSync: String?
    var bridgeReachable: Bool
}

struct LinkedInConfigStatus: Decodable {
    var configured: Bool
    var email: String?
    var hasSession: Bool
    var lastSync: String?
}

struct LinkedInConfigPayload: Encodable {
    var email: String
    var password: String
}

/// `dict(_state)` verbatim from sync_linkedin.py. `log`/`categoryCounts` are
/// declared on the frontend's TS type but never actually populated by the
/// backend — kept optional here since they'll always decode as absent.
struct LinkedInSyncState: Decodable {
    var status: String
    var step: String
    var processed: Int
    var total: Int
    var created: Int
    var updated: Int
    var skipped: Int
    var errors: [String]
    var startedAt: String?
    var finishedAt: String?
}

struct LinkedInMessagesStatus: Decodable {
    var conversationCount: Int
    var lastImportedAt: String?
}

struct LinkedInMessagesImportResult: Decodable {
    var conversationsImported: Int
    var conversationsUpdated: Int
    var eventsCreated: Int
    var errors: [String]
}

struct CompanySyncStatus: Decodable {
    var running: Bool
    var currentCompany: String?
    var pending: Int
    var done: Int
    var failed: Int
    var needsReview: Int
    var profiles: [CompanySyncProfileItem]
}

struct CompanySyncProfileItem: Decodable, Identifiable {
    var id: Int
    var nameDisplay: String?
    var syncStatus: String
    var syncError: String?
    var lastSyncedAt: String?
}

/// `POST /api/sync/company/run`'s response: `message` is only present when
/// `started == false` (the field is genuinely absent, not null, on success).
struct CompanySyncRunResult: Decodable {
    var started: Bool
    var count: Int
    var message: String?
}

struct FilesSyncStatus: Decodable {
    var enabled: Bool
    var folderPath: String?
    var lastSync: String?
    var bridgeReachable: Bool
}

/// Candidate item for the targeted (per-application) manual sync/assign
/// flow. `id > 0` is a real PendingMatch id, `id < 0` is `-(Event.id)` from
/// another application, `id == 0` is a live/unsaved candidate.
struct ManualCandidate: Decodable, Identifiable {
    var id: Int
    var source: String
    var externalId: String?
    var eventType: String?
    var datum: String?
    var titel: String?
    var extract: String?
    var confidence: Int
    var suggestedAppId: Int?
    var suggestedAppFirma: String?
}

struct ManualAssignPayload: Encodable {
    var matchId: Int
    var externalId: String?
    var source: String?
    var eventType: String?
    var datum: String?
    var titel: String?
    var removeFromOther: Bool = false
}

/// `sync_targeted.py`'s `/assign` response has three distinct shapes
/// depending on branch (created, conflict, or override-created) — modeled
/// as one optional-heavy struct rather than three, since `conflict` alone
/// discriminates which fields are meaningful.
struct ManualAssignResult: Decodable {
    var conflict: Bool
    var eventId: Int?
    var conflictAppId: Int?
    var conflictAppFirma: String?
    var conflictEventId: Int?
}

struct TargetedResetResult: Decodable {
    var deletedEvents: Int
    var deletedItems: Int
}

/// `GET /api/sync/targeted/{id}/result` before completion is just
/// `{"done": false}` — every other field is only present once finished.
struct TargetedSyncResult: Decodable {
    var done: Bool
    var created: Int?
    var skipped: Int?
    var processed: Int?
    var errors: [String]?
}
