import Foundation

private struct OkResponse: Decodable { var ok: Bool }
private struct URLResponseBody: Decodable { var url: String }

/// Wraps settings.py's key/value config endpoints (prefix "/api/settings").
/// Ollama model pull is intentionally not wrapped here — it's a
/// Server-Sent-Events stream (`text/event-stream`), not a single JSON
/// response, and would need a dedicated streaming client.
struct SettingsAPI {
    let client: APIClient

    func aiSettings() async throws -> AiSettings {
        try await client.request("/settings/ai")
    }

    @discardableResult
    func updateAiSettings(_ payload: AiSettingsPayload) async throws -> AiSettings {
        try await client.request("/settings/ai", method: .post, body: payload)
    }

    @discardableResult
    func deleteAiKey() async throws -> AiSettings {
        try await client.request("/settings/ai/key", method: .delete)
    }

    func testAiSettings() async throws -> AiTestResult {
        try await client.request("/settings/ai/test", method: .post)
    }

    func mapsSettings() async throws -> MapsSettings {
        try await client.request("/settings/maps")
    }

    @discardableResult
    func updateMapsSettings(_ payload: MapsSettingsPayload) async throws -> MapsSettings {
        try await client.request("/settings/maps", method: .post, body: payload)
    }

    @discardableResult
    func deleteMapsKey() async throws -> MapsSettings {
        try await client.request("/settings/maps/key", method: .delete)
    }

    func agentSettings() async throws -> AgentSettings {
        try await client.request("/settings/agent")
    }

    @discardableResult
    func updateAgentSettings(_ payload: AgentSettingsPayload) async throws -> AgentSettings {
        try await client.request("/settings/agent", method: .post, body: payload)
    }

    @discardableResult
    func deleteAgentToken() async throws -> AgentSettings {
        try await client.request("/settings/agent/token", method: .delete)
    }

    func agentHealth() async throws -> AgentHealth {
        try await client.request("/settings/agent/health")
    }

    func logoSettings() async throws -> LogoSettings {
        try await client.request("/settings/logo")
    }

    @discardableResult
    func updateLogoSettings(_ payload: LogoSettingsPayload) async throws -> LogoSettings {
        try await client.request("/settings/logo", method: .post, body: payload)
    }

    func syncSettings() async throws -> SyncSettingsFlags {
        try await client.request("/settings/sync")
    }

    @discardableResult
    func updateSyncSettings(_ flags: SyncSettingsFlags) async throws -> SyncSettingsFlags {
        try await client.request("/settings/sync", method: .post, body: flags)
    }

    func filesSettings() async throws -> FilesSettings {
        try await client.request("/settings/files")
    }

    @discardableResult
    func updateFilesSettings(_ payload: FilesSettingsPayload) async throws -> FilesSettings {
        try await client.request("/settings/files", method: .post, body: payload)
    }
}
