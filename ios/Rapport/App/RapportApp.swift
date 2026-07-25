import SwiftUI

@main
struct RapportApp: App {
    @State private var session: SessionStore = {
        let args = ProcessInfo.processInfo.arguments
        // UI tests pass -uiTesting so every run starts from a clean slate
        // (no leftover server address/token from a previous test/run on the
        // same simulator) rather than depending on external test-order setup.
        if args.contains("-uiTesting") {
            ServerConfigStore().clear()
            KeychainHelper.delete("rapport_auth_token")
        }
        // -uiTestingMockAPI additionally routes every request through
        // MockURLProtocol and pre-seeds a server address + token, so UI
        // tests can drive authenticated screens (Applications, Kanban,
        // detail) without a real backend or driving the login form.
        if args.contains("-uiTestingMockAPI") {
            MockURLProtocol.installDefaultUITestResponses()
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [MockURLProtocol.self]
            let configStore = ServerConfigStore()
            configStore.baseURL = URL(string: "http://mock.local")
            KeychainHelper.set("mock-token", for: "rapport_auth_token")
            return SessionStore(configStore: configStore, client: APIClient(session: URLSession(configuration: config)))
        }
        return SessionStore()
    }()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(session)
                .task {
                    await session.restoreSession()
                }
        }
    }
}
