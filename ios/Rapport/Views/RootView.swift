import SwiftUI

/// Top-level router: server address -> auth -> main app. Each stage's view
/// owns just its own step; this view only decides which one is visible.
struct RootView: View {
    @Environment(SessionStore.self) private var session

    var body: some View {
        Group {
            if !session.isServerConfigured {
                ServerSetupView()
            } else if !session.isAuthenticated {
                AuthFlowView()
            } else {
                MainSplitView()
            }
        }
        .animation(.default, value: session.isServerConfigured)
        .animation(.default, value: session.isAuthenticated)
    }
}
