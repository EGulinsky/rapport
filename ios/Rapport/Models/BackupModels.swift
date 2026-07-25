import Foundation

/// `backups` entries come straight from the external Rapport Agent, never
/// validated against a Pydantic model on the backend — every field is
/// optional so a shape change on the agent side can't crash this decode.
struct BackupEntry: Decodable, Identifiable {
    var name: String?
    var path: String?
    var modified: Double?
    var size: Int?

    var id: String { path ?? name ?? UUID().uuidString }
}

struct BackupStatus: Decodable {
    var enabled: Bool
    var backupFolder: String?
    var frequencyHours: Int
    var keepCount: Int
    var keepDaily: Int
    var keepWeekly: Int
    var lastBackup: String?
    var backups: [BackupEntry]?
}

struct BackupSettingsPayload: Encodable {
    var enabled: Bool
    var backupFolder: String?
    var frequencyHours: Int = 24
    var keepCount: Int = 7
    var keepDaily: Int = 14
    var keepWeekly: Int = 8
}

struct BackupRunResult: Decodable {
    var success: Bool
    var filename: String
}

struct BackupRestorePayload: Encodable {
    var filename: String
    var folder: String
}

struct BackupRestoreFilePayload: Encodable {
    var path: String
}
