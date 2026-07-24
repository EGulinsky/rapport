import SwiftUI

@main
struct RapportApp: App {
    @State private var session: SessionStore = {
        // UI tests pass -uiTesting so every run starts from a clean slate
        // (no leftover server address/token from a previous test/run on the
        // same simulator) rather than depending on external test-order setup.
        if ProcessInfo.processInfo.arguments.contains("-uiTesting") {
            ServerConfigStore().clear()
            KeychainHelper.delete("rapport_auth_token")
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
