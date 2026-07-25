import Foundation
import Observation

/// Single source of truth for "where's the server" + "who's logged in",
/// consumed by RootView to decide which screen to show. Mirrors the web
/// app's AuthContext (token in storage, current user fetched via /auth/me)
/// plus the extra server-address step a self-hosted native client needs.
@MainActor
@Observable
final class SessionStore {
    private static let tokenKey = "rapport_auth_token"

    private let configStore: ServerConfigStore
    let client: APIClient

    var applications: ApplicationsAPI { ApplicationsAPI(client: client) }
    var contacts: ContactsAPI { ContactsAPI(client: client) }
    var companies: CompaniesAPI { CompaniesAPI(client: client) }
    var calendar: CalendarAPI { CalendarAPI(client: client) }
    var analytics: AnalyticsAPI { AnalyticsAPI(client: client) }
    var settings: SettingsAPI { SettingsAPI(client: client) }
    var syncProgress: SyncProgressAPI { SyncProgressAPI(client: client) }
    var googleSync: GoogleSyncAPI { GoogleSyncAPI(client: client) }
    var icloudSync: ICloudSyncAPI { ICloudSyncAPI(client: client) }
    var filesSync: FilesSyncAPI { FilesSyncAPI(client: client) }
    var linkedinSync: LinkedInSyncAPI { LinkedInSyncAPI(client: client) }
    var companySync: CompanySyncAPI { CompanySyncAPI(client: client) }
    var targetedSync: TargetedSyncAPI { TargetedSyncAPI(client: client) }
    var backup: BackupAPI { BackupAPI(client: client) }

    private(set) var serverURL: URL?
    private(set) var currentUser: UserResponse?
    var isLoading = false
    var lastError: APIError?

    /// Set right after register() succeeds so the UI can route straight to
    /// the verification-code screen with the email pre-filled.
    var pendingVerificationEmail: String?

    var isServerConfigured: Bool { serverURL != nil }
    var isAuthenticated: Bool { currentUser != nil }

    init(configStore: ServerConfigStore = ServerConfigStore(), client: APIClient = APIClient()) {
        self.configStore = configStore
        self.client = client
        self.serverURL = configStore.baseURL

        NotificationCenter.default.addObserver(
            forName: .rapportUnauthorized, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.logout() }
        }
    }

    /// Called once at app launch to restore a previous session (server URL +
    /// token both already on disk) without making the user re-enter anything.
    func restoreSession() async {
        guard let serverURL else { return }
        await client.updateBaseURL(serverURL)
        guard let token = KeychainHelper.get(Self.tokenKey) else { return }
        await client.updateToken(token)
        await fetchCurrentUser()
    }

    func configureServer(rawInput: String) throws {
        guard let url = ServerConfigStore.normalize(rawInput) else {
            throw APIError(message: "Enter a valid server address, e.g. http://192.168.1.50:8000", errorKey: nil, statusCode: nil)
        }
        configStore.baseURL = url
        serverURL = url
        Task { await client.updateBaseURL(url) }
    }

    func resetServer() {
        configStore.clear()
        serverURL = nil
        logout()
    }

    // MARK: - Auth

    func register(email: String, password: String, uiLanguage: String) async throws {
        isLoading = true
        defer { isLoading = false }
        let _: MessageResponse = try await client.request(
            "/auth/register", method: .post,
            body: RegisterPayload(email: email, password: password, uiLanguage: uiLanguage)
        )
        pendingVerificationEmail = email
    }

    func verifyEmail(email: String, code: String) async throws {
        isLoading = true
        defer { isLoading = false }
        let response: AuthTokenResponse = try await client.request(
            "/auth/verify-email", method: .post,
            body: VerifyEmailPayload(email: email, code: code)
        )
        pendingVerificationEmail = nil
        try await applyToken(response.accessToken)
    }

    func resendCode(email: String) async throws {
        let _: MessageResponse = try await client.request(
            "/auth/resend-code", method: .post,
            body: ResendCodePayload(email: email)
        )
    }

    func login(email: String, password: String) async throws {
        isLoading = true
        defer { isLoading = false }
        let response: AuthTokenResponse = try await client.request(
            "/auth/login", method: .post,
            body: LoginPayload(email: email, password: password)
        )
        try await applyToken(response.accessToken)
    }

    func logout() {
        KeychainHelper.delete(Self.tokenKey)
        currentUser = nil
        Task { await client.updateToken(nil) }
    }

    private func applyToken(_ token: String) async throws {
        KeychainHelper.set(token, for: Self.tokenKey)
        await client.updateToken(token)
        await fetchCurrentUser()
    }

    func fetchCurrentUser() async {
        do {
            currentUser = try await client.request("/auth/me") as UserResponse
        } catch {
            currentUser = nil
        }
    }

    // MARK: - Profile

    func updateProfile(_ payload: ProfilePayload) async throws {
        currentUser = try await client.request("/auth/profile", method: .patch, body: payload)
    }

    func changePassword(oldPassword: String, newPassword: String) async throws {
        let _: MessageResponse = try await client.request(
            "/auth/change-password", method: .post,
            body: ChangePasswordPayload(oldPassword: oldPassword, newPassword: newPassword)
        )
    }

    func uploadCV(data: Data, filename: String, mimeType: String) async throws {
        currentUser = try await client.uploadMultipart("/auth/cv", fieldName: "file", filename: filename, mimeType: mimeType, data: data)
    }

    func deleteCV() async throws {
        currentUser = try await client.request("/auth/cv", method: .delete)
    }
}
