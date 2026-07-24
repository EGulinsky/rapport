import SwiftUI

struct RegisterView: View {
    @Environment(SessionStore.self) private var session
    let onBackToLogin: () -> Void

    @State private var email = ""
    @State private var password = ""
    @State private var uiLanguage = "en"
    @State private var errorMessage: String?

    var body: some View {
        Form {
            Section {
                TextField("Email", text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Password (min. 8 characters)", text: $password)
                    .textContentType(.newPassword)
                Picker("Language", selection: $uiLanguage) {
                    Text("English").tag("en")
                    Text("Deutsch").tag("de")
                }
            }

            if let errorMessage {
                Section {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }

            Section {
                Button {
                    register()
                } label: {
                    if session.isLoading {
                        ProgressView()
                    } else {
                        Text("Create account")
                    }
                }
                .disabled(email.isEmpty || password.count < 8 || session.isLoading)

                Button("Back to login", action: onBackToLogin)
            }
        }
        .navigationTitle("Create account")
    }

    private func register() {
        errorMessage = nil
        Task {
            do {
                try await session.register(email: email, password: password, uiLanguage: uiLanguage)
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
        RegisterView(onBackToLogin: {})
            .environment(SessionStore())
    }
}
