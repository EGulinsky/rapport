import SwiftUI

struct BackupSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: BackupSettingsViewModel?
    @State private var enabled = false
    @State private var folder = ""
    @State private var frequencyHours = 24
    @State private var keepCount = 7
    @State private var keepDaily = 14
    @State private var keepWeekly = 8

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("Configuration") {
                        Toggle("Automatic backups", isOn: $enabled)
                        TextField("Backup folder", text: $folder)
                        Stepper("Every \(frequencyHours)h", value: $frequencyHours, in: 1...168)
                        Stepper("Keep \(keepCount) hourly", value: $keepCount, in: 0...100)
                        Stepper("Keep \(keepDaily) daily", value: $keepDaily, in: 0...100)
                        Stepper("Keep \(keepWeekly) weekly", value: $keepWeekly, in: 0...100)
                        Button("Save settings") {
                            Task {
                                await viewModel.updateSettings(
                                    enabled: enabled, folder: folder, frequencyHours: frequencyHours,
                                    keepCount: keepCount, keepDaily: keepDaily, keepWeekly: keepWeekly
                                )
                            }
                        }
                    }
                    Section("Manual backup") {
                        if let lastBackup = viewModel.status?.lastBackup {
                            Text("Last backup: \(lastBackup.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Run backup now") { Task { await viewModel.runBackup() } }
                        if let message = viewModel.lastRunMessage {
                            Text(message).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if let backups = viewModel.status?.backups, !backups.isEmpty {
                        Section("Available backups") {
                            ForEach(backups) { backup in
                                HStack {
                                    Text(backup.name ?? "Backup")
                                    Spacer()
                                    if let size = backup.size {
                                        Text(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file))
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                .contextMenu {
                                    Button("Restore") {
                                        guard let name = backup.name else { return }
                                        Task { await viewModel.restore(filename: name, folder: folder) }
                                    }
                                }
                            }
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
        .navigationTitle("Backup")
        .task {
            if viewModel == nil {
                viewModel = BackupSettingsViewModel(api: session.backup)
            }
            await viewModel?.load()
            if let status = viewModel?.status {
                enabled = status.enabled
                folder = status.backupFolder ?? ""
                frequencyHours = status.frequencyHours
                keepCount = status.keepCount
                keepDaily = status.keepDaily
                keepWeekly = status.keepWeekly
            }
        }
    }
}
