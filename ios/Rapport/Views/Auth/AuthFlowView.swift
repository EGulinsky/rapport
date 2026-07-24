import SwiftUI

/// Switches between login/register/verify-email based on what the user is
/// doing and what SessionStore reports (e.g. jumps straight to verification
/// right after a successful register(), since the backend requires a code
/// before login works at all).
struct AuthFlowView: View {
    private enum Stage {
        case login, register
    }

    @Environment(SessionStore.self) private var session
    @State private var stage: Stage = .login

    var body: some View {
        NavigationStack {
            Group {
                if session.pendingVerificationEmail != nil {
                    VerifyEmailView()
                } else if stage == .login {
                    LoginView(onCreateAccount: { stage = .register })
                } else {
                    RegisterView(onBackToLogin: { stage = .login })
                }
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Change server") {
                        session.resetServer()
                    }
                }
            }
        }
    }
}
