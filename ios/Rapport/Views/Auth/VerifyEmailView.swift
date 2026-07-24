import SwiftUI

struct VerifyEmailView: View {
    @Environment(SessionStore.self) private var session
    @State private var code = ""
    @State private var errorMessage: String?
    @State private var resendMessage: String?

    private var email: String { session.pendingVerificationEmail ?? "" }

    var body: some View {
        Form {
            Section {
                Text("We sent a verification code to \(email). Enter it below to finish creating your account.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Section {
                TextField("Verification code", text: $code)
                    .keyboardType(.numberPad)
                    .onSubmit(verify)
            }

            if let errorMessage {
                Section { Text(errorMessage).foregroundStyle(.red) }
            }
            if let resendMessage {
                Section { Text(resendMessage).foregroundStyle(.secondary) }
            }

            Section {
                Button {
                    verify()
                } label: {
                    if session.isLoading {
                        ProgressView()
                    } else {
                        Text("Verify")
                    }
                }
                .disabled(code.isEmpty || session.isLoading)

                Button("Resend code", action: resend)
                Button("Cancel", role: .cancel) {
                    session.pendingVerificationEmail = nil
                }
            }
        }
        .navigationTitle("Verify email")
    }

    private func verify() {
        errorMessage = nil
        Task {
            do {
                try await session.verifyEmail(email: email, code: code)
            } catch let error as APIError {
                errorMessage = error.message
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func resend() {
        errorMessage = nil
        Task {
            do {
                try await session.resendCode(email: email)
                resendMessage = "A new code has been sent."
            } catch let error as APIError {
                errorMessage = error.message
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}

#Preview {
    NavigationStack {
        VerifyEmailView()
            .environment(SessionStore())
    }
}
