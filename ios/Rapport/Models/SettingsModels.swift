import Foundation

struct AiSettings: Decodable {
    var provider: String
    var model: String
    var hasKey: Bool
    var baseUrl: String?
    var enabled: Bool
}

struct AiSettingsPayload: Encodable {
    var provider: String
    var model: String
    var apiKey: String?
    var baseUrl: String?
    var enabled: Bool = true
}

struct AiTestResult: Decodable {
    var status: String
    var message: String
}

struct MapsSettings: Decodable {
    var hasKey: Bool
}

struct MapsSettingsPayload: Encodable {
    var apiKey: String?
}

struct AgentSettings: Decodable {
    var url: String?
    var hasToken: Bool
}

struct AgentSettingsPayload: Encodable {
    var url: String?
    var token: String?
}

struct AgentHealthModule: Decodable {
    var ok: Bool
    var error: String?
    var phoneAccessible: Bool?
    var whatsappAccessible: Bool?
}

struct AgentHealth: Decodable {
    var reachable: Bool
    var version: String?
    var platform: String?
    var modules: [String: AgentHealthModule]
    var error: String?
}

struct LogoSettings: Decodable {
    var apiKey: String?
}

struct LogoSettingsPayload: Encodable {
    var apiKey: String?
}

/// GET/POST /api/settings/sync — one bool per source toggle plus the
/// audit-log verbosity string. Both directions share this exact shape.
struct SyncSettingsFlags: Codable {
    var googleEnabled: Bool
    var gmailEnabled: Bool
    var gcalEnabled: Bool
    var icloudEnabled: Bool
    var icloudMailEnabled: Bool
    var icloudCalEnabled: Bool
    var icloudNotesEnabled: Bool
    var icloudRemindersEnabled: Bool
    var icloudContactsEnabled: Bool
    var icloudCallsEnabled: Bool
    var linkedinEnabled: Bool
    var filesEnabled: Bool
    var auditLogLevel: String
}

struct FilesSettings: Decodable {
    var folderPath: String?
    var enabled: Bool
    var lastSync: Date?
}

struct FilesSettingsPayload: Encodable {
    var folderPath: String?
    var enabled: Bool?
}
