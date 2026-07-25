import SwiftUI

struct ICloudSyncSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: ICloudSyncViewModel?
    @State private var appleId = ""
    @State private var appPassword = ""
    @State private var icloudEmail = ""
    @State private var twoFACode = ""

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("Connection") {
                        if let status = viewModel.status, status.connected {
                            Label("Connected as \(status.appleId ?? "")", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                            Button("Disconnect", role: .destructive) { Task { await viewModel.disconnect() } }
                        } else {
                            TextField("Apple ID", text: $appleId)
                                .textInputAutocapitalization(.never)
                            SecureField("App-specific password", text: $appPassword)
                            TextField("iCloud email (if different)", text: $icloudEmail)
                                .textInputAutocapitalization(.never)
                            Button("Save credentials") {
                                Task { await viewModel.saveCredentials(appleId: appleId, appPassword: appPassword, icloudEmail: icloudEmail, webPassword: "") }
                            }
                        }
                    }

                    Section("Mail") {
                        if let lastSync = viewModel.status?.mailLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncMail() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.resetMail() } }
                        if let progress = viewModel.progressStore.progress["icloud_mail"] { SyncProgressRow(progress: progress) }
                    }

                    Section("Calendar") {
                        if let lastSync = viewModel.status?.calendarLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncCalendar() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.resetCalendar() } }
                        if let progress = viewModel.progressStore.progress["icloud_cal"] { SyncProgressRow(progress: progress) }
                    }

                    Section("Reminders") {
                        if let lastSync = viewModel.status?.remindersLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncReminders() } }
                        if let progress = viewModel.progressStore.progress["icloud_reminders"] { SyncProgressRow(progress: progress) }
                    }

                    Section("Contacts") {
                        if let lastSync = viewModel.status?.contactsLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncContacts() } }
                    }

                    Section("Notes") {
                        if let lastSync = viewModel.status?.notesLastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.syncNotes() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.resetNotes() } }
                        if let progress = viewModel.progressStore.progress["icloud_notes"] { SyncProgressRow(progress: progress) }
                        if viewModel.notes2FARequired {
                            TextField("2FA code", text: $twoFACode)
                            Button("Verify") { Task { await viewModel.verifyNotes2FA(code: twoFACode) } }
                        }
                    }

                    Section("Calls") {
                        if let callsStatus = viewModel.callsStatus {
                            Toggle("Enabled", isOn: Binding(
                                get: { callsStatus.enabled },
                                set: { newValue in Task { await viewModel.setCallsEnabled(newValue) } }
                            ))
                            Label(callsStatus.bridgeReachable ? "Bridge reachable" : "Bridge unreachable",
                                  systemImage: callsStatus.bridgeReachable ? "checkmark.circle" : "exclamationmark.triangle")
                                .font(.caption)
                                .foregroundStyle(callsStatus.bridgeReachable ? .green : .orange)
                            if let lastSync = callsStatus.lastSync {
                                Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                            }
                        }
                        Button("Sync now") { Task { await viewModel.syncCalls() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.resetCalls() } }
                        if let progress = viewModel.progressStore.progress["icloud_calls"] { SyncProgressRow(progress: progress) }
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Section { Text(errorMessage).foregroundStyle(.red) }
                    }
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("iCloud")
        .task {
            if viewModel == nil {
                viewModel = ICloudSyncViewModel(api: session.icloudSync, progressStore: SyncProgressStore(api: session.syncProgress))
            }
            await viewModel?.load()
        }
    }
}
