import Foundation
import Observation

@MainActor
@Observable
final class GoogleSyncViewModel {
    private let api: GoogleSyncAPI
    let progressStore: SyncProgressStore

    private(set) var status: GoogleSyncStatus?
    var isLoading = false
    var errorMessage: String?

    init(api: GoogleSyncAPI, progressStore: SyncProgressStore) {
        self.api = api
        self.progressStore = progressStore
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveCredentials(clientId: String, clientSecret: String) async {
        errorMessage = nil
        do {
            status = try await api.saveCredentials(clientId: clientId, clientSecret: clientSecret)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func disconnect() async {
        do {
            try await api.disconnect()
            status = GoogleSyncStatus(connected: false, clientId: nil, gmailLastSync: nil, gcalLastSync: nil)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func syncGmail() async {
        progressStore.watch("gmail")
        do { _ = try await api.syncGmail() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }

    func resetGmail() async {
        do { try await api.resetGmail() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }

    func syncCalendar() async {
        progressStore.watch("gcal")
        do { _ = try await api.syncCalendar() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }

    func resetCalendar() async {
        do { try await api.resetCalendar() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }
}

@MainActor
@Observable
final class ICloudSyncViewModel {
    private let api: ICloudSyncAPI
    let progressStore: SyncProgressStore

    private(set) var status: ICloudSyncStatus?
    private(set) var callsStatus: CallsStatus?
    var isLoading = false
    var errorMessage: String?
    var notes2FARequired = false

    init(api: ICloudSyncAPI, progressStore: SyncProgressStore) {
        self.api = api
        self.progressStore = progressStore
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await api.status()
            callsStatus = try await api.callsStatus()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveCredentials(appleId: String, appPassword: String, icloudEmail: String, webPassword: String) async {
        errorMessage = nil
        do {
            status = try await api.saveCredentials(
                appleId: appleId, appPassword: appPassword,
                icloudEmail: icloudEmail.isEmpty ? nil : icloudEmail,
                webPassword: webPassword.isEmpty ? nil : webPassword
            )
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func disconnect() async {
        do {
            try await api.disconnect()
            status = ICloudSyncStatus(connected: false, appleId: nil, icloudEmail: nil, mailLastSync: nil, calendarLastSync: nil, remindersLastSync: nil, contactsLastSync: nil, notesLastSync: nil)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func run(_ source: String, _ action: () async throws -> Void) async {
        progressStore.watch(source)
        do { try await action() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }

    func syncMail() async { await run("icloud_mail") { _ = try await self.api.syncMail() } }
    func resetMail() async { do { try await api.resetMail() } catch { errorMessage = "\(error)" } }

    func syncCalendar() async { await run("icloud_cal") { _ = try await self.api.syncCalendar() } }
    func resetCalendar() async { do { try await api.resetCalendar() } catch { errorMessage = "\(error)" } }

    func syncReminders() async { await run("icloud_reminders") { _ = try await self.api.syncReminders() } }
    func resetReminders() async { do { try await api.resetReminders() } catch { errorMessage = "\(error)" } }

    /// The synchronous, real-result endpoint (not a background stub like
    /// the other iCloud sources) — reload status right after so
    /// `contactsLastSync` reflects the just-finished run immediately.
    func syncContacts() async {
        errorMessage = nil
        do {
            _ = try await api.syncContacts()
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    func resetContacts() async { do { try await api.resetContacts() } catch { errorMessage = "\(error)" } }

    func syncNotes() async { await run("icloud_notes") { _ = try await self.api.syncNotes() } }
    func resetNotes() async { do { try await api.resetNotes() } catch { errorMessage = "\(error)" } }

    func verifyNotes2FA(code: String) async {
        errorMessage = nil
        do {
            _ = try await api.verifyNotes2FA(code: code)
            notes2FARequired = false
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setCallsEnabled(_ enabled: Bool) async {
        do { callsStatus = try await api.setCallsEnabled(enabled) } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }

    func syncCalls() async { await run("icloud_calls") { _ = try await self.api.syncCalls() } }
    func resetCalls() async { do { try await api.resetCalls() } catch { errorMessage = "\(error)" } }
}

@MainActor
@Observable
final class FilesSyncViewModel {
    private let api: FilesSyncAPI
    let progressStore: SyncProgressStore

    private(set) var status: FilesSyncStatus?
    var isLoading = false
    var errorMessage: String?

    init(api: FilesSyncAPI, progressStore: SyncProgressStore) {
        self.api = api
        self.progressStore = progressStore
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func sync() async {
        progressStore.watch("local_files")
        do { _ = try await api.sync() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }

    func reset() async {
        do { try await api.reset() } catch let error as APIError { errorMessage = error.message } catch { errorMessage = error.localizedDescription }
    }
}

@MainActor
@Observable
final class LinkedInSyncViewModel {
    private let api: LinkedInSyncAPI

    private(set) var config: LinkedInConfigStatus?
    private(set) var syncState: LinkedInSyncState?
    private(set) var messagesStatus: LinkedInMessagesStatus?
    var isLoading = false
    var errorMessage: String?
    var importResultMessage: String?

    private var pollTask: Task<Void, Never>?

    init(api: LinkedInSyncAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            config = try await api.configStatus()
            messagesStatus = try? await api.messagesStatus()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveConfig(email: String, password: String) async {
        errorMessage = nil
        do {
            config = try await api.saveConfig(email: email, password: password)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteConfig() async {
        do {
            try await api.deleteConfig()
            config = try? await api.configStatus()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearSession() async {
        do {
            try await api.clearSession()
            config = try? await api.configStatus()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func run(targetAppId: Int? = nil) async {
        errorMessage = nil
        do {
            syncState = try await api.run(targetAppId: targetAppId)
            startPolling()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func submit2FA(code: String) async {
        do {
            try await api.submit2FA(code: code)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                guard let state = try? await self.api.syncStatus() else { break }
                self.syncState = state
                if state.status != "running" { break }
                try? await Task.sleep(nanoseconds: 1_500_000_000)
            }
        }
    }

    func importMessages(csvData: Data, filename: String) async {
        errorMessage = nil
        importResultMessage = nil
        do {
            let result = try await api.importMessages(csvData: csvData, filename: filename)
            importResultMessage = "\(result.conversationsImported) imported, \(result.conversationsUpdated) updated, \(result.eventsCreated) events created"
            messagesStatus = try? await api.messagesStatus()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
@Observable
final class CompanySyncViewModel {
    private let api: CompanySyncAPI

    private(set) var status: CompanySyncStatus?
    var isLoading = false
    var errorMessage: String?
    private var pollTask: Task<Void, Never>?

    init(api: CompanySyncAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func run(force: Bool = false) async {
        errorMessage = nil
        do {
            _ = try await api.run(force: force)
            startPolling()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func cancel() async {
        do {
            try await api.cancel()
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                guard let latest = try? await self.api.status() else { break }
                self.status = latest
                if !latest.running { break }
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }
}

@MainActor
@Observable
final class BackupSettingsViewModel {
    private let api: BackupAPI

    private(set) var status: BackupStatus?
    var isLoading = false
    var errorMessage: String?
    var lastRunMessage: String?

    init(api: BackupAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateSettings(enabled: Bool, folder: String, frequencyHours: Int, keepCount: Int, keepDaily: Int, keepWeekly: Int) async {
        errorMessage = nil
        do {
            status = try await api.updateSettings(BackupSettingsPayload(
                enabled: enabled, backupFolder: folder.isEmpty ? nil : folder,
                frequencyHours: frequencyHours, keepCount: keepCount, keepDaily: keepDaily, keepWeekly: keepWeekly
            ))
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runBackup() async {
        errorMessage = nil
        do {
            let result = try await api.run()
            lastRunMessage = result.success ? "Backup created: \(result.filename)" : "Backup failed"
            status = try await api.status()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func restore(filename: String, folder: String) async {
        errorMessage = nil
        do {
            let result = try await api.restore(filename: filename, folder: folder)
            lastRunMessage = result.success ? "Restored \(result.filename)" : "Restore failed"
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
