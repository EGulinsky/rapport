import SwiftUI

struct AgentSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: AgentSettingsViewModel?
    @State private var url = ""
    @State private var token = ""

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("Rapport Agent") {
                        Text("The native macOS helper app that gives sync access to Mail, Calendar, Contacts, Calls, and local files.")
                            .font(.caption).foregroundStyle(.secondary)
                        TextField("Agent URL", text: $url)
                            .textInputAutocapitalization(.never)
                        if viewModel.settings?.hasToken == true {
                            Label("Token configured", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                        }
                        SecureField("Token", text: $token)
                        Button("Save") {
                            Task { await viewModel.save(url: url, token: token.isEmpty ? nil : token) }
                        }
                        if viewModel.settings?.hasToken == true {
                            Button("Remove token", role: .destructive) { Task { await viewModel.deleteToken() } }
                        }
                    }
                    if let health = viewModel.health {
                        Section("Health") {
                            Label(health.reachable ? "Reachable" : "Unreachable", systemImage: health.reachable ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundStyle(health.reachable ? .green : .red)
                            if let version = health.version {
                                Text("Version \(version)").font(.caption).foregroundStyle(.secondary)
                            }
                            if let platform = health.platform {
                                Text(platform).font(.caption).foregroundStyle(.secondary)
                            }
                            ForEach(Array(health.modules.keys.sorted()), id: \.self) { key in
                                if let module = health.modules[key] {
                                    HStack {
                                        Text(key)
                                        Spacer()
                                        Image(systemName: module.ok ? "checkmark.circle" : "exclamationmark.triangle")
                                            .foregroundStyle(module.ok ? .green : .orange)
                                    }
                                }
                            }
                            Button("Refresh health") { Task { await viewModel.refreshHealth() } }
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
        .navigationTitle("Rapport Agent")
        .task {
            if viewModel == nil {
                viewModel = AgentSettingsViewModel(api: session.settings)
            }
            await viewModel?.load()
            url = viewModel?.settings?.url ?? ""
        }
    }
}
