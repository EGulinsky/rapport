import Foundation

/// applications.py and contacts.py's merge endpoints require `fieldOverrides`
/// (even if empty); companies.py's defaults to `{}` server-side. Always
/// sending an explicit empty dict from the client works for all three and
/// means "keep the winner's own values for every field" — this app doesn't
/// offer a per-field conflict-resolution UI (yet), just winner-take-all.
struct MergeRequestPayload: Encodable {
    var winnerId: Int
    var loserIds: [Int]
    var fieldOverrides: [String: Int] = [:]
}

struct MergeResult: Decodable {
    var success: Bool
    var winnerId: Int
}
