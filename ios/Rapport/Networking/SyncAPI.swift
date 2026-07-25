import Foundation

private struct OkResponse: Decodable { var ok: Bool }
private struct AuthURLResponse: Decodable { var url: String }
private struct ImportCountResponse: Decodable { var imported: Int; var skipped: Int }

/// The shared progress/batch-results poll. Despite the URL living under the
/// Google router, it aggregates every sync source in the app — call this
/// once and read whichever source keys you care about.
struct SyncProgressAPI {
    let client: APIClient

    func progress() async throws -> [String: ProgressEntry] {
        try await client.request("/sync/google/progress")
    }

    func batchResults() async throws -> [String: BatchResult] {
        try await client.request("/sync/google/batch/results")
    }
}

struct GoogleSyncAPI {
    let client: APIClient

    func status() async throws -> GoogleSyncStatus {
        try await client.request("/sync/google/status")
    }

    @discardableResult
    func saveCredentials(clientId: String, clientSecret: String) async throws -> GoogleSyncStatus {
        try await client.request(
            "/sync/google/credentials", method: .post,
            body: GoogleCredentialsPayload(clientId: clientId, clientSecret: clientSecret)
        )
    }

    func authURL() async throws -> String {
        let response: AuthURLResponse = try await client.request("/sync/google/auth")
        return response.url
    }

    func disconnect() async throws {
        try await client.requestVoid("/sync/google", method: .delete)
    }

    func resetGmail() async throws { try await client.requestVoid("/sync/google/gmail/reset", method: .post) }
    func syncGmail() async throws -> SyncResult { try await client.request("/sync/google/gmail", method: .post) }
    func resetCalendar() async throws { try await client.requestVoid("/sync/google/calendar/reset", method: .post) }
    func syncCalendar() async throws -> SyncResult { try await client.request("/sync/google/calendar", method: .post) }
}

struct ICloudSyncAPI {
    let client: APIClient

    func status() async throws -> ICloudSyncStatus {
        try await client.request("/sync/icloud/status")
    }

    @discardableResult
    func saveCredentials(appleId: String, appPassword: String, icloudEmail: String?, webPassword: String?) async throws -> ICloudSyncStatus {
        try await client.request(
            "/sync/icloud/credentials", method: .post,
            body: ICloudCredentialsPayload(appleId: appleId, appPassword: appPassword, icloudEmail: icloudEmail, webPassword: webPassword)
        )
    }

    func setWebPassword(_ password: String) async throws {
        try await client.requestVoid("/sync/icloud/web-password", method: .post, body: ICloudWebPasswordPayload(code: password))
    }

    func test() async throws -> AiTestResult {
        try await client.request("/sync/icloud/test", method: .post)
    }

    func disconnect() async throws {
        try await client.requestVoid("/sync/icloud", method: .delete)
    }

    func resetMail() async throws { try await client.requestVoid("/sync/icloud/mail/reset", method: .post) }
    func syncMail() async throws -> SyncResult { try await client.request("/sync/icloud/mail", method: .post) }

    func resetNotes() async throws { try await client.requestVoid("/sync/icloud/notes/reset", method: .post) }
    func syncNotes() async throws -> SyncResult { try await client.request("/sync/icloud/notes", method: .post) }
    func verifyNotes2FA(code: String) async throws -> SyncResult {
        try await client.request("/sync/icloud/notes/verify-2fa", method: .post, body: TwoFACodePayload(code: code))
    }

    func resetCalendar() async throws { try await client.requestVoid("/sync/icloud/calendar/reset", method: .post) }
    func syncCalendar() async throws -> SyncResult { try await client.request("/sync/icloud/calendar", method: .post) }

    func resetReminders() async throws { try await client.requestVoid("/sync/icloud/reminders/reset", method: .post) }
    func syncReminders() async throws -> SyncResult { try await client.request("/sync/icloud/reminders", method: .post) }

    func resetContacts() async throws { try await client.requestVoid("/sync/icloud/contacts/reset", method: .post) }
    func syncContacts() async throws -> SyncResult { try await client.request("/sync/icloud/contacts", method: .post) }

    func callsStatus() async throws -> CallsStatus {
        try await client.request("/sync/icloud/calls/status")
    }

    @discardableResult
    func setCallsEnabled(_ enabled: Bool) async throws -> CallsStatus {
        try await client.request("/sync/icloud/calls/settings", method: .post, body: ["enabled": enabled])
    }

    func resetCalls() async throws { try await client.requestVoid("/sync/icloud/calls/reset", method: .post) }
    func syncCalls() async throws -> SyncResult { try await client.request("/sync/icloud/calls", method: .post) }
}

struct FilesSyncAPI {
    let client: APIClient

    func status() async throws -> FilesSyncStatus {
        try await client.request("/sync/files/status")
    }

    func reset() async throws { try await client.requestVoid("/sync/files/reset", method: .post) }
    func sync() async throws -> SyncResult { try await client.request("/sync/files", method: .post) }
}

struct LinkedInSyncAPI {
    let client: APIClient

    func configStatus() async throws -> LinkedInConfigStatus {
        try await client.request("/sync/linkedin/config")
    }

    @discardableResult
    func saveConfig(email: String, password: String) async throws -> LinkedInConfigStatus {
        try await client.request("/sync/linkedin/config", method: .post, body: LinkedInConfigPayload(email: email, password: password))
    }

    func deleteConfig() async throws {
        try await client.requestVoid("/sync/linkedin/config", method: .delete)
    }

    func syncStatus() async throws -> LinkedInSyncState {
        try await client.request("/sync/linkedin/status")
    }

    @discardableResult
    func run(targetAppId: Int? = nil) async throws -> LinkedInSyncState {
        try await client.request("/sync/linkedin/run", method: .post, body: ["target_app_id": targetAppId])
    }

    func clearSession() async throws {
        try await client.requestVoid("/sync/linkedin/clear-session", method: .post)
    }

    func submit2FA(code: String) async throws {
        try await client.requestVoid("/sync/linkedin/submit-2fa", method: .post, body: TwoFACodePayload(code: code))
    }

    func syncProfile() async throws {
        try await client.requestVoid("/sync/linkedin/profile", method: .post)
    }

    func messagesStatus() async throws -> LinkedInMessagesStatus {
        try await client.request("/sync/linkedin/messages/status")
    }

    func importMessages(csvData: Data, filename: String) async throws -> LinkedInMessagesImportResult {
        try await client.uploadMultipart(
            "/sync/linkedin/messages/import",
            fieldName: "file", filename: filename, mimeType: "text/csv", data: csvData
        )
    }
}

struct CompanySyncAPI {
    let client: APIClient

    func status() async throws -> CompanySyncStatus {
        try await client.request("/sync/company/status")
    }

    func run(force: Bool = false, companyIds: [Int]? = nil) async throws -> CompanySyncRunResult {
        var query: [String: String?] = ["force": force ? "true" : "false"]
        if let companyIds {
            query["company_ids"] = companyIds.map(String.init).joined(separator: ",")
        }
        return try await client.request("/sync/company/run", method: .post, query: query)
    }

    func cancel() async throws { try await client.requestVoid("/sync/company/cancel", method: .post) }
    func resetLock() async throws { try await client.requestVoid("/sync/company/reset-lock", method: .post) }
    func resetFailed() async throws { try await client.requestVoid("/sync/company/reset-failed", method: .post) }
    func resetProfile(_ id: Int) async throws { try await client.requestVoid("/sync/company/profiles/\(id)/reset", method: .post) }
}

/// Per-application manual/targeted sync — the "candidate assignment" flow
/// surfaced from an individual Application's detail view.
struct TargetedSyncAPI {
    let client: APIClient

    func reset(appId: Int) async throws -> TargetedResetResult {
        try await client.request("/sync/targeted/\(appId)/reset", method: .post)
    }

    @discardableResult
    func trigger(appId: Int) async throws -> SyncResult {
        try await client.request("/sync/targeted/\(appId)", method: .post)
    }

    func result(appId: Int) async throws -> TargetedSyncResult {
        try await client.request("/sync/targeted/\(appId)/result")
    }

    func candidates(appId: Int, query: String? = nil) async throws -> [ManualCandidate] {
        try await client.request("/sync/targeted/\(appId)/candidates", query: ["q": query])
    }

    func assign(appId: Int, payload: ManualAssignPayload) async throws -> ManualAssignResult {
        try await client.request("/sync/targeted/\(appId)/assign", method: .post, body: payload)
    }
}
