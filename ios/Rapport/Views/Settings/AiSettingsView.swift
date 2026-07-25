import SwiftUI

struct AiSettingsView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: AiSettingsViewModel?
    @State private var provider = "openai"
    @State private var model = ""
    @State private var apiKey = ""
    @State private var baseUrl = ""
    @State private var enabled = true

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("AI provider") {
                        Picker("Provider", selection: $provider) {
                            Text("OpenAI").tag("openai")
                            Text("Anthropic").tag("anthropic")
                            Text("Ollama").tag("ollama")
                        }
                        TextField("Model", text: $model)
                        if provider == "ollama" {
                            TextField("Base URL", text: $baseUrl)
                        } else {
                            if viewModel.settings?.hasKey == true {
                                Label("API key configured", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                            }
                            SecureField("API key", text: $apiKey)
                        }
                        Toggle("Enabled", isOn: $enabled)
                        Button("Save") {
                            Task { await viewModel.save(provider: provider, model: model, apiKey: apiKey, baseUrl: baseUrl, enabled: enabled) }
                        }
                        Button("Test connection") { Task { await viewModel.test() } }
                        if viewModel.settings?.hasKey == true {
                            Button("Remove key", role: .destructive) { Task { await viewModel.deleteKey() } }
                        }
                        if let testResultMessage = viewModel.testResultMessage {
                            Text(testResultMessage).font(.caption).foregroundStyle(.secondary)
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
        .navigationTitle("AI assessment")
        .task {
            if viewModel == nil {
                viewModel = AiSettingsViewModel(api: session.settings)
            }
            await viewModel?.load()
            if let settings = viewModel?.settings {
                provider = settings.provider
                model = settings.model
                baseUrl = settings.baseUrl ?? ""
                enabled = settings.enabled
            }
        }
    }
}
