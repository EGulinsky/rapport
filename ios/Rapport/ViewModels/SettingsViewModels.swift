import Foundation
import Observation

@MainActor
@Observable
final class AccountSettingsViewModel {
    private let session: SessionStore

    var isSaving = false
    var errorMessage: String?
    var cvUploadMessage: String?

    init(session: SessionStore) {
        self.session = session
    }

    func saveProfile(vorname: String, nachname: String, linkedinUrl: String, homeLocation: String) async {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            try await session.updateProfile(ProfilePayload(
                vorname: vorname.isEmpty ? nil : vorname,
                nachname: nachname.isEmpty ? nil : nachname,
                linkedinUrl: linkedinUrl.isEmpty ? nil : linkedinUrl,
                homeLocation: homeLocation.isEmpty ? nil : homeLocation,
                uiLanguage: nil
            ))
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setLanguage(_ language: String) async {
        do {
            try await session.updateProfile(ProfilePayload(uiLanguage: language))
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func changePassword(oldPassword: String, newPassword: String) async -> Bool {
        errorMessage = nil
        do {
            try await session.changePassword(oldPassword: oldPassword, newPassword: newPassword)
            return true
        } catch let error as APIError {
            errorMessage = error.message
            return false
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func uploadCV(data: Data, filename: String, mimeType: String) async {
        errorMessage = nil
        do {
            try await session.uploadCV(data: data, filename: filename, mimeType: mimeType)
            cvUploadMessage = "Uploaded \(filename)"
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteCV() async {
        errorMessage = nil
        do {
            try await session.deleteCV()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
@Observable
final class SyncControlViewModel {
    private let api: SettingsAPI

    private(set) var flags: SyncSettingsFlags?
    var isLoading = false
    var errorMessage: String?

    init(api: SettingsAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            flags = try await api.syncSettings()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func update(_ newFlags: SyncSettingsFlags) async {
        do {
            flags = try await api.updateSyncSettings(newFlags)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Shared shape for the three simple "single API key" panels (Maps, Logo)
/// plus the Agent url/token panel, all following the same
/// get-status/save/delete pattern.
@MainActor
@Observable
final class ApiKeySettingsViewModel<Status> {
    private let loadFn: () async throws -> Status
    private let saveFn: (String) async throws -> Status
    private let deleteFn: (() async throws -> Status)?

    private(set) var status: Status?
    var isLoading = false
    var errorMessage: String?

    init(
        load: @escaping () async throws -> Status,
        save: @escaping (String) async throws -> Status,
        delete: (() async throws -> Status)? = nil
    ) {
        self.loadFn = load
        self.saveFn = save
        self.deleteFn = delete
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await loadFn()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save(_ key: String) async {
        errorMessage = nil
        do {
            status = try await saveFn(key)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func delete() async {
        guard let deleteFn else { return }
        errorMessage = nil
        do {
            status = try await deleteFn()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
@Observable
final class AgentSettingsViewModel {
    private let api: SettingsAPI

    private(set) var settings: AgentSettings?
    private(set) var health: AgentHealth?
    var isLoading = false
    var errorMessage: String?

    init(api: SettingsAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            settings = try await api.agentSettings()
            health = try? await api.agentHealth()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save(url: String, token: String?) async {
        errorMessage = nil
        do {
            settings = try await api.updateAgentSettings(AgentSettingsPayload(url: url.isEmpty ? nil : url, token: token))
            health = try? await api.agentHealth()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteToken() async {
        do {
            settings = try await api.deleteAgentToken()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshHealth() async {
        health = try? await api.agentHealth()
    }
}

@MainActor
@Observable
final class AiSettingsViewModel {
    private let api: SettingsAPI

    private(set) var settings: AiSettings?
    var isLoading = false
    var errorMessage: String?
    var testResultMessage: String?

    init(api: SettingsAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            settings = try await api.aiSettings()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save(provider: String, model: String, apiKey: String?, baseUrl: String?, enabled: Bool) async {
        errorMessage = nil
        do {
            settings = try await api.updateAiSettings(AiSettingsPayload(
                provider: provider, model: model,
                apiKey: apiKey?.isEmpty == true ? nil : apiKey,
                baseUrl: baseUrl?.isEmpty == true ? nil : baseUrl,
                enabled: enabled
            ))
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteKey() async {
        do {
            settings = try await api.deleteAiKey()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func test() async {
        testResultMessage = nil
        do {
            let result = try await api.testAiSettings()
            testResultMessage = result.message
        } catch let error as APIError {
            testResultMessage = error.message
        } catch {
            testResultMessage = error.localizedDescription
        }
    }
}
