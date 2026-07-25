import SwiftUI
import UniformTypeIdentifiers

struct AccountSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: AccountSettingsViewModel?

    @State private var vorname = ""
    @State private var nachname = ""
    @State private var linkedinUrl = ""
    @State private var homeLocation = ""
    @State private var language = "en"
    @State private var oldPassword = ""
    @State private var newPassword = ""
    @State private var showCvImporter = false
    @State private var passwordChangedMessage: String?

    var body: some View {
        Form {
            Section("Profile") {
                TextField("First name", text: $vorname)
                TextField("Last name", text: $nachname)
                TextField("LinkedIn URL", text: $linkedinUrl)
                    .textInputAutocapitalization(.never)
                TextField("Home location", text: $homeLocation)
                Button("Save profile") {
                    Task { await viewModel?.saveProfile(vorname: vorname, nachname: nachname, linkedinUrl: linkedinUrl, homeLocation: homeLocation) }
                }
            }

            Section("Language") {
                Picker("App language", selection: $language) {
                    Text("English").tag("en")
                    Text("Deutsch").tag("de")
                }
                .onChange(of: language) { _, newValue in
                    Task { await viewModel?.setLanguage(newValue) }
                }
            }

            Section("CV") {
                if let filename = session.currentUser?.cvFilename {
                    HStack {
                        Text(filename)
                        Spacer()
                        if let size = session.currentUser?.cvSizeBytes {
                            Text(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file))
                                .foregroundStyle(.secondary)
                        }
                    }
                    Button("Remove CV", role: .destructive) {
                        Task { await viewModel?.deleteCV() }
                    }
                } else {
                    Text("No CV uploaded").foregroundStyle(.secondary)
                }
                Button("Upload CV") { showCvImporter = true }
                if let message = viewModel?.cvUploadMessage {
                    Text(message).font(.caption).foregroundStyle(.secondary)
                }
            }

            Section("Change password") {
                SecureField("Current password", text: $oldPassword)
                SecureField("New password", text: $newPassword)
                Button("Change password") {
                    Task {
                        let ok = await viewModel?.changePassword(oldPassword: oldPassword, newPassword: newPassword) ?? false
                        if ok {
                            passwordChangedMessage = "Password changed."
                            oldPassword = ""
                            newPassword = ""
                        }
                    }
                }
                .disabled(oldPassword.isEmpty || newPassword.isEmpty)
                if let passwordChangedMessage {
                    Text(passwordChangedMessage).font(.caption).foregroundStyle(.green)
                }
            }

            if let errorMessage = viewModel?.errorMessage {
                Section {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Account")
        .fileImporter(isPresented: $showCvImporter, allowedContentTypes: [.pdf, .plainText, .rtf, UTType(filenameExtension: "docx") ?? .data]) { result in
            guard case let .success(url) = result else { return }
            guard url.startAccessingSecurityScopedResource() else { return }
            defer { url.stopAccessingSecurityScopedResource() }
            guard let data = try? Data(contentsOf: url) else { return }
            let mimeType = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
            Task { await viewModel?.uploadCV(data: data, filename: url.lastPathComponent, mimeType: mimeType) }
        }
        .task {
            if viewModel == nil {
                viewModel = AccountSettingsViewModel(session: session)
            }
            if let user = session.currentUser {
                vorname = user.vorname ?? ""
                nachname = user.nachname ?? ""
                linkedinUrl = user.linkedinUrl ?? ""
                homeLocation = user.homeLocation ?? ""
                language = user.uiLanguage
            }
        }
    }
}
