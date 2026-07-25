import Foundation

private struct PathResponse: Decodable { var path: String }

/// Wraps backup.py (prefix "/api/backup"). The native folder/file pickers
/// (`pick-folder`/`pick-file`) proxy through the macOS Rapport Agent and
/// only make sense when the backend itself runs on a Mac the agent is
/// paired with — exposed here for completeness but the iOS UI lets the
/// user type a path directly as the primary path.
struct BackupAPI {
    let client: APIClient

    func status() async throws -> BackupStatus {
        try await client.request("/backup/status")
    }

    @discardableResult
    func updateSettings(_ payload: BackupSettingsPayload) async throws -> BackupStatus {
        try await client.request("/backup/settings", method: .post, body: payload)
    }

    func run() async throws -> BackupRunResult {
        try await client.request("/backup/run", method: .post)
    }

    func pickFolder() async throws -> String {
        let response: PathResponse = try await client.request("/backup/pick-folder")
        return response.path
    }

    func restore(filename: String, folder: String) async throws -> BackupRunResult {
        try await client.request("/backup/restore", method: .post, body: BackupRestorePayload(filename: filename, folder: folder))
    }

    func pickFile() async throws -> String {
        let response: PathResponse = try await client.request("/backup/pick-file")
        return response.path
    }

    func restoreFile(path: String) async throws -> BackupRunResult {
        try await client.request("/backup/restore-file", method: .post, body: BackupRestoreFilePayload(path: path))
    }
}
