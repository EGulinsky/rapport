import SwiftUI

struct GoogleSyncSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: GoogleSyncViewModel?
    @State private var clientId = ""
    @State private var clientSecret = ""

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("Connection") {
                        if let status = viewModel.status, status.connected {
                            Label("Connected", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                            Button("Disconnect", role: .destructive) { Task { await viewModel.disconnect() } }
                        } else {
                            TextField("Client ID", text: $clientId)
                                .textInputAutocapitalization(.never)
                            SecureField("Client secret", text: $clientSecret)
                            Button("Save credentials") {
                                Task { await viewModel.saveCredentials(clientId: clientId, clientSecret: clientSecret) }
                            }
                        }
                    }

                    Section("Gmail") {
                        if let lastSync = viewModel.status?.gmailLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncGmail() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.resetGmail() } }
                        if let progress = viewModel.progressStore.progress["gmail"] {
                            SyncProgressRow(progress: progress)
                        }
                    }

                    Section("Google Calendar") {
                        if let lastSync = viewModel.status?.gcalLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncCalendar() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.resetCalendar() } }
                        if let progress = viewModel.progressStore.progress["gcal"] {
                            SyncProgressRow(progress: progress)
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
        .navigationTitle("Google")
        .task {
            if viewModel == nil {
                viewModel = GoogleSyncViewModel(api: session.googleSync, progressStore: SyncProgressStore(api: session.syncProgress))
            }
            await viewModel?.load()
        }
    }
}
