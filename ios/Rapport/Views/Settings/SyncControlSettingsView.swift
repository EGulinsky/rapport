import SwiftUI

struct SyncControlSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: SyncControlViewModel?

    var body: some View {
        Group {
            if let viewModel, var flags = viewModel.flags {
                Form {
                    Section("Google") {
                        Toggle("Google sync enabled", isOn: Binding(
                            get: { flags.googleEnabled },
                            set: { flags.googleEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Gmail", isOn: Binding(
                            get: { flags.gmailEnabled },
                            set: { flags.gmailEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Google Calendar", isOn: Binding(
                            get: { flags.gcalEnabled },
                            set: { flags.gcalEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                    }
                    Section("iCloud") {
                        Toggle("iCloud sync enabled", isOn: Binding(
                            get: { flags.icloudEnabled },
                            set: { flags.icloudEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Mail", isOn: Binding(
                            get: { flags.icloudMailEnabled },
                            set: { flags.icloudMailEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Calendar", isOn: Binding(
                            get: { flags.icloudCalEnabled },
                            set: { flags.icloudCalEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Notes", isOn: Binding(
                            get: { flags.icloudNotesEnabled },
                            set: { flags.icloudNotesEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Reminders", isOn: Binding(
                            get: { flags.icloudRemindersEnabled },
                            set: { flags.icloudRemindersEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Contacts", isOn: Binding(
                            get: { flags.icloudContactsEnabled },
                            set: { flags.icloudContactsEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Calls", isOn: Binding(
                            get: { flags.icloudCallsEnabled },
                            set: { flags.icloudCallsEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                    }
                    Section("Other sources") {
                        Toggle("LinkedIn", isOn: Binding(
                            get: { flags.linkedinEnabled },
                            set: { flags.linkedinEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                        Toggle("Local files", isOn: Binding(
                            get: { flags.filesEnabled },
                            set: { flags.filesEnabled = $0; Task { await viewModel.update(flags) } }
                        ))
                    }
                    Section("Audit log") {
                        Picker("Verbosity", selection: Binding(
                            get: { flags.auditLogLevel },
                            set: { flags.auditLogLevel = $0; Task { await viewModel.update(flags) } }
                        )) {
                            Text("Off").tag("off")
                            Text("Normal").tag("normal")
                            Text("Verbose").tag("verbose")
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
        .navigationTitle("Sync sources")
        .task {
            if viewModel == nil {
                viewModel = SyncControlViewModel(api: session.settings)
                await viewModel?.load()
            }
        }
    }
}
