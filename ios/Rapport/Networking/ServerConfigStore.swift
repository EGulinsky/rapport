import Foundation

/// Persists the self-hosted backend's base URL (e.g. "http://192.168.1.50:8000")
/// entered during onboarding. Unlike the web app (served from the same origin
/// as its API), this app can run on a physically separate device from the
/// Docker host, so the address must be user-supplied rather than assumed.
@MainActor
final class ServerConfigStore {
    private static let key = "rapport_server_base_url"
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    var baseURL: URL? {
        get {
            guard let raw = defaults.string(forKey: Self.key) else { return nil }
            return URL(string: raw)
        }
        set {
            defaults.set(newValue?.absoluteString, forKey: Self.key)
        }
    }

    func clear() {
        defaults.removeObject(forKey: Self.key)
    }

    /// Normalizes user input into a valid base URL: adds a scheme if missing
    /// (defaulting to http, since a LAN backend rarely has a TLS cert) and
    /// strips a trailing slash so path-joining stays simple everywhere else.
    static func normalize(_ input: String) -> URL? {
        var trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if !trimmed.contains("://") {
            trimmed = "http://\(trimmed)"
        }
        while trimmed.hasSuffix("/") {
            trimmed.removeLast()
        }
        return URL(string: trimmed)
    }
}
