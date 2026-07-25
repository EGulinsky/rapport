import Foundation

/// Wraps review.py's PendingMatch queue (prefix "/api/review").
struct ReviewAPI {
    let client: APIClient

    func count() async throws -> Int {
        let response: ReviewCountResult = try await client.request("/review/count")
        return response.count
    }

    func list() async throws -> [PendingMatchRead] {
        try await client.request("/review/")
    }

    func approve(matchId: Int, payload: ApproveMatchPayload) async throws -> ApproveMatchResult {
        try await client.request("/review/\(matchId)/approve", method: .post, body: payload)
    }

    func reject(matchId: Int) async throws -> RejectMatchResult {
        try await client.request("/review/\(matchId)", method: .delete)
    }
}

/// Wraps audit_log.py (prefix "/api/audit").
struct AuditLogAPI {
    let client: APIClient

    func list(appId: Int? = nil, contactId: Int? = nil, companyProfileId: Int? = nil, eventId: Int? = nil, entityType: String? = nil, limit: Int = 200, offset: Int = 0) async throws -> AuditLogResponse {
        try await client.request("/audit/", query: [
            "app_id": appId.map(String.init),
            "contact_id": contactId.map(String.init),
            "company_profile_id": companyProfileId.map(String.init),
            "event_id": eventId.map(String.init),
            "entity_type": entityType,
            "limit": String(limit),
            "offset": String(offset)
        ])
    }
}

/// Wraps merge.py (prefix "/api/merge"). Winner-take-all — no per-field
/// override UI, `fieldOverrides` is always sent empty.
struct MergeAPI {
    let client: APIClient

    func mergeApplications(winnerId: Int, loserIds: [Int]) async throws -> MergeResult {
        try await client.request("/merge/applications", method: .post, body: MergeRequestPayload(winnerId: winnerId, loserIds: loserIds))
    }

    func mergeContacts(winnerId: Int, loserIds: [Int]) async throws -> MergeResult {
        try await client.request("/merge/contacts", method: .post, body: MergeRequestPayload(winnerId: winnerId, loserIds: loserIds))
    }

    func mergeCompanies(winnerId: Int, loserIds: [Int]) async throws -> MergeResult {
        try await client.request("/merge/companies", method: .post, body: MergeRequestPayload(winnerId: winnerId, loserIds: loserIds))
    }
}
