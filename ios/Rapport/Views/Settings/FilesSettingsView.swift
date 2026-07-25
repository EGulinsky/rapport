import SwiftUI

struct FilesSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: FilesSyncViewModel?
    @State private var folderPath = ""
    @State private var enabled = false

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section {
                        TextField("Folder path", text: $folderPath)
                        Toggle("Enabled", isOn: $enabled)
                        Button("Save") {
                            Task {
                                try? await session.settings.updateFilesSettings(FilesSettingsPayload(folderPath: folderPath.isEmpty ? nil : folderPath, enabled: enabled))
                                await viewModel.load()
                            }
                        }
                    }
                    Section {
                        if let lastSync = viewModel.status?.lastSync {
                            Text("Last sync: \(lastSync.formatted())").foregroundStyle(.secondary)
                        }
                        Button("Sync now") { Task { await viewModel.sync() } }
                        Button("Reset", role: .destructive) { Task { await viewModel.reset(); await viewModel.load() } }
                        if let progress = viewModel.progressStore.progress["local_files"] {
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
        .navigationTitle("Local files")
        .task {
            if viewModel == nil {
                viewModel = FilesSyncViewModel(api: session.filesSync, progressStore: SyncProgressStore(api: session.syncProgress))
            }
            await viewModel?.load()
            folderPath = viewModel?.status?.folderPath ?? ""
            enabled = viewModel?.status?.enabled ?? false
        }
    }
}

/// Shared row rendering one `ProgressEntry` — the per-category counts
/// (created/updated/skipped) mirror the web SyncButton's detailed progress.
struct SyncProgressRow: View {
    let progress: ProgressEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(progress.step).font(.caption)
                Spacer()
                Text("\(progress.percent)%").font(.caption).foregroundStyle(.secondary)
            }
            ProgressView(value: Double(progress.percent), total: 100)
            if progress.done {
                Text("Created \(progress.created) · Updated \(progress.updated) · Skipped \(progress.skipped)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
