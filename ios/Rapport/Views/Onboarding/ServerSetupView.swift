import SwiftUI

/// First screen a fresh install shows: rapport is self-hosted, so there's no
/// fixed backend address to bake into the app — the user points it at their
/// own Docker host (typically a LAN address like http://192.168.1.50:8000).
struct ServerSetupView: View {
    @Environment(SessionStore.self) private var session
    @State private var input = ""
    @State private var errorMessage: String?
    @State private var discovery = ServerDiscoveryViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Spacer()

                VStack(spacing: 8) {
                    Image(systemName: "server.rack")
                        .font(.system(size: 48))
                        .foregroundStyle(.tint)
                    Text("Connect to your Rapport server")
                        .font(.title2.bold())
                    Text("Enter the address of the Rapport instance running on your network, e.g. http://192.168.1.50:8000")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                }

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
                .padding(.horizontal, 32)

                Button("Continue", action: connect)
                    .buttonStyle(.borderedProminent)
                    .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
                    .accessibilityIdentifier("serverContinueButton")

                discoverySection

                Spacer()
                Spacer()
            }
            .padding()
            .navigationTitle("Setup")
            .navigationBarTitleDisplayMode(.inline)
        }
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
        .padding(.horizontal, 32)
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
