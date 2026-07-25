import SwiftUI

/// Shared UI for the single-API-key panels (Maps, Company logos) — both
/// follow the same masked-key / save / delete pattern as Settings' Maps
/// and Logo panels on the web.
struct ApiKeySettingsView<Status>: View {
    let title: String
    let helpText: String
    let hasKey: (Status) -> Bool
    @State var viewModel: ApiKeySettingsViewModel<Status>
    let supportsDelete: Bool

    @State private var keyInput = ""

    init(
        title: String,
        helpText: String,
        supportsDelete: Bool = true,
        hasKey: @escaping (Status) -> Bool,
        load: @escaping () async throws -> Status,
        save: @escaping (String) async throws -> Status,
        delete: (() async throws -> Status)? = nil
    ) {
        self.title = title
        self.helpText = helpText
        self.supportsDelete = supportsDelete
        self.hasKey = hasKey
        _viewModel = State(initialValue: ApiKeySettingsViewModel(load: load, save: save, delete: delete))
    }

    var body: some View {
        Form {
            Section {
                Text(helpText).font(.caption).foregroundStyle(.secondary)
                if let status = viewModel.status, hasKey(status) {
                    Label("API key configured", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                }
                SecureField("API key", text: $keyInput)
                Button("Save") {
                    Task { await viewModel.save(keyInput); keyInput = "" }
                }
                .disabled(keyInput.isEmpty)
                if supportsDelete {
                    Button("Remove key", role: .destructive) {
                        Task { await viewModel.delete() }
                    }
                }
            }
            if let errorMessage = viewModel.errorMessage {
                Section { Text(errorMessage).foregroundStyle(.red) }
            }
        }
        .navigationTitle(title)
        .task { await viewModel.load() }
    }
}
