import SwiftUI
import UniformTypeIdentifiers

struct LinkedInSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: LinkedInSyncViewModel?
    @State private var email = ""
    @State private var password = ""
    @State private var twoFACode = ""
    @State private var showCsvImporter = false

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("Connection") {
                        if let config = viewModel.config, config.configured {
                            Label("Configured (\(config.email ?? ""))", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                            Text(config.hasSession ? "Session active" : "No active session").font(.caption).foregroundStyle(.secondary)
                            Button("Clear session") { Task { await viewModel.clearSession() } }
                            Button("Remove configuration", role: .destructive) { Task { await viewModel.deleteConfig() } }
                        } else {
                            TextField("Email", text: $email)
                                .textInputAutocapitalization(.never)
                            SecureField("Password", text: $password)
                            Button("Save") { Task { await viewModel.saveConfig(email: email, password: password) } }
                        }
                    }

                    Section("Job sync") {
                        Button("Sync now") { Task { await viewModel.run() } }
                        if let state = viewModel.syncState {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(state.step).font(.caption)
                                if state.total > 0 {
                                    ProgressView(value: Double(state.processed), total: Double(state.total))
                                }
                                Text("Created \(state.created) · Updated \(state.updated) · Skipped \(state.skipped)")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                            if state.status == "needs_2fa" {
                                TextField("2FA code", text: $twoFACode)
                                Button("Submit code") { Task { await viewModel.submit2FA(code: twoFACode) } }
                            }
                        }
                    }

                    Section("Messages import") {
                        Text("Upload the messages.csv file from your LinkedIn data export to attach LinkedIn conversations to matching contacts.")
                            .font(.caption).foregroundStyle(.secondary)
                        if let status = viewModel.messagesStatus {
                            Text("\(status.conversationCount) conversations imported")
                            if let lastImportedAt = status.lastImportedAt {
                                Text("Last imported: \(lastImportedAt.formatted())").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Button("Import messages.csv") { showCsvImporter = true }
                        if let message = viewModel.importResultMessage {
                            Text(message).font(.caption).foregroundStyle(.secondary)
                        }
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Section { Text(errorMessage).foregroundStyle(.red) }
                    }
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("LinkedIn")
        .fileImporter(isPresented: $showCsvImporter, allowedContentTypes: [.commaSeparatedText]) { result in
            guard case let .success(url) = result else { return }
            guard url.startAccessingSecurityScopedResource() else { return }
            defer { url.stopAccessingSecurityScopedResource() }
            guard let data = try? Data(contentsOf: url) else { return }
            Task { await viewModel?.importMessages(csvData: data, filename: url.lastPathComponent) }
        }
        .task {
            if viewModel == nil {
                viewModel = LinkedInSyncViewModel(api: session.linkedinSync)
            }
            await viewModel?.load()
        }
    }
}
