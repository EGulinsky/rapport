import SwiftUI

/// First screen a fresh install shows: rapport is self-hosted, so there's no
/// fixed backend address to bake into the app — the user points it at their
/// own Docker host (typically a LAN address like http://192.168.1.50:8000).
struct ServerSetupView: View {
    @Environment(SessionStore.self) private var session
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @State private var input = ""
    @State private var errorMessage: String?
    @State private var discovery = ServerDiscoveryViewModel()

    var body: some View {
        NavigationStack {
            Group {
                // On iPad (regular width) a single centered column leaves
                // most of the screen empty. A split layout — branding on
                // one side, the actual form on the other — uses that width
                // instead of just floating in the middle of it. iPhone
                // (compact width) keeps the original stacked layout, where
                // there's no spare width to split.
                if horizontalSizeClass == .regular {
                    HStack(spacing: 0) {
                        brandingPanel
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .background(Color.accentColor.opacity(0.1))
                        formPanel
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 24) {
                            brandingPanel
                            formPanel
                        }
                        .padding(.vertical, 32)
                    }
                }
            }
            .navigationTitle("Setup")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var brandingPanel: some View {
        VStack(spacing: 10) {
            Image(systemName: "server.rack")
                .font(.system(size: 48))
                .foregroundStyle(.tint)
            Text("Rapport")
                .font(.title.bold())
            Text("Your self-hosted job search, tracked from first application to signed offer.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
    }

    private var formPanel: some View {
        VStack(spacing: 20) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Connect to your server")
                    .font(.title3.bold())
                Text("Enter the address of the Rapport instance running on your network, e.g. http://192.168.1.50:8000")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            VStack(alignment: .leading, spacing: 8) {
                TextField("Server address", text: $input)
                    .textFieldStyle(.roundedBorder)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.go)
                    .onSubmit(connect)
                    .accessibilityIdentifier("serverAddressField")

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }

            Button("Continue", action: connect)
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: .infinity)
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
                .accessibilityIdentifier("serverContinueButton")

            HStack {
                Rectangle().fill(.separator).frame(height: 0.5)
                Text("or").font(.caption).foregroundStyle(.secondary)
                Rectangle().fill(.separator).frame(height: 0.5)
            }

            discoverySection
        }
        .padding(.horizontal, 40)
        .frame(maxWidth: 420)
    }

    @ViewBuilder
    private var discoverySection: some View {
        VStack(spacing: 12) {
            Button {
                Task { await discovery.scan() }
            } label: {
                if discovery.isScanning {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("Scanning local network…")
                    }
                } else {
                    Label("Find server on local network", systemImage: "wifi")
                }
            }
            .disabled(discovery.isScanning)
            .accessibilityIdentifier("discoverServerButton")

            if let errorMessage = discovery.errorMessage {
                Text(errorMessage).font(.caption).foregroundStyle(.secondary)
            }

            ForEach(discovery.discoveredServers) { server in
                Button {
                    input = server.baseURLString
                    connect()
                } label: {
                    HStack {
                        Image(systemName: "server.rack")
                        Text(server.baseURLString)
                        Spacer()
                        Image(systemName: "chevron.right")
                    }
                }
                .buttonStyle(.bordered)
            }
        }
    }

    private func connect() {
        do {
            try session.configureServer(rawInput: input)
            errorMessage = nil
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

#Preview {
    ServerSetupView()
        .environment(SessionStore())
}
