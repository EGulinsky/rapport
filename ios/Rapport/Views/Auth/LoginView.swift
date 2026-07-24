import SwiftUI

struct LoginView: View {
    @Environment(SessionStore.self) private var session
    let onCreateAccount: () -> Void

    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?

    var body: some View {
        Form {
            Section {
                TextField("Email", text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("loginEmailField")
                SecureField("Password", text: $password)
                    .textContentType(.password)
                    .onSubmit(login)
                    .accessibilityIdentifier("loginPasswordField")
            }

            if let errorMessage {
                Section {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }

            Section {
                Button {
                    login()
                } label: {
                    if session.isLoading {
                        ProgressView()
                    } else {
                        Text("Log in")
                    }
                }
                .disabled(email.isEmpty || password.isEmpty || session.isLoading)
                .accessibilityIdentifier("loginSubmitButton")

                Button("Create account", action: onCreateAccount)
                    .accessibilityIdentifier("goToRegisterButton")
            }
        }
        .navigationTitle("Rapport")
    }

    private func login() {
        errorMessage = nil
        Task {
            do {
                try await session.login(email: email, password: password)
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
        LoginView(onCreateAccount: {})
            .environment(SessionStore())
    }
}
