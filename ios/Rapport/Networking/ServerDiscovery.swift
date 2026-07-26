import Foundation

struct DiscoveredServer: Identifiable, Hashable {
    var host: String
    var port: Int

    var id: String { "\(host):\(port)" }
    var baseURLString: String { "http://\(host):\(port)" }
}

/// Finds a running Rapport backend on the local Wi-Fi network so the user
/// doesn't have to type an IP address by hand during onboarding.
///
/// Deliberately a plain client-side subnet scan rather than Bonjour/mDNS:
/// the backend runs inside a Docker container (docker-compose), and a
/// container-side mDNS advertisement wouldn't bind to the host Mac's real
/// LAN interface without Docker host-networking, which OrbStack/Docker
/// Desktop on macOS doesn't support the same way Linux does. A scan from
/// the *client* against the LAN the backend's port is already published
/// on sidesteps that entirely — it's exactly what typing the IP in by hand
/// already does, just automated.
///
/// Fingerprint: FastAPI auto-serves `/openapi.json` unauthenticated with
/// `info.title` set to the app's configured title ("rapport API",
/// backend/app/main.py) — enough to identify a real Rapport backend
/// without any backend changes or a dedicated discovery endpoint.
enum ServerDiscovery {
    static let defaultPort = 8000
    static let fingerprintTitle = "rapport API"

    /// Scans the given /24 subnet (e.g. "192.168.1") for a Rapport backend
    /// on `port`, probing all 254 host addresses concurrently with a short
    /// per-request timeout. Returns as soon as scanning finishes; callers
    /// needing progress should just show an indeterminate spinner — a full
    /// /24 sweep takes a couple of seconds on typical Wi-Fi.
    static func scan(subnet: String, port: Int = defaultPort) async -> [DiscoveredServer] {
        await withTaskGroup(of: DiscoveredServer?.self) { group in
            for host in candidateHosts(subnet: subnet) {
                group.addTask {
                    await probe(host: host, port: port)
                }
            }
            var found: [DiscoveredServer] = []
            for await result in group {
                if let result { found.append(result) }
            }
            return found.sorted { $0.host < $1.host }
        }
    }

    /// The 254 usable host addresses in a /24 (`.1` through `.254`) — covers
    /// the overwhelming majority of home/office Wi-Fi networks. A /16 or
    /// other mask would need a different range; not attempted here since
    /// scanning a /16 (65k hosts) isn't practical for a quick onboarding scan.
    static func candidateHosts(subnet: String) -> [String] {
        (1...254).map { "\(subnet).\($0)" }
    }

    /// Derives the "a.b.c" prefix from this device's current Wi-Fi IPv4
    /// address (e.g. "192.168.1.42" -> "192.168.1"), or nil if no active
    /// non-loopback IPv4 interface is found (no network connection).
    static func currentSubnetPrefix() -> String? {
        currentIPv4Address().flatMap(subnetPrefix(fromIPv4Address:))
    }

    /// Pure string-slicing half of `currentSubnetPrefix()`, split out so it's
    /// unit-testable without depending on this device's actual network
    /// interfaces (the other half, `currentIPv4Address()`, calls into
    /// `getifaddrs` and can't be meaningfully unit-tested).
    static func subnetPrefix(fromIPv4Address address: String) -> String? {
        let parts = address.split(separator: ".")
        guard parts.count == 4 else { return nil }
        return parts[0...2].joined(separator: ".")
    }

    private static func probe(host: String, port: Int) async -> DiscoveredServer? {
        guard let url = URL(string: "http://\(host):\(port)/openapi.json") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 1.0
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }
            guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let info = object["info"] as? [String: Any],
                  let title = info["title"] as? String,
                  title == fingerprintTitle
            else { return nil }
            return DiscoveredServer(host: host, port: port)
        } catch {
            return nil
        }
    }

    /// Reads this device's own IPv4 address off the active `en0`/`en1`-style
    /// interface via `getifaddrs` (the same low-level approach `ipconfig`
    /// itself uses) — no public/async API gives this directly.
    private static func currentIPv4Address() -> String? {
        var address: String?
        var ifaddrPointer: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddrPointer) == 0, let firstAddr = ifaddrPointer else { return nil }
        defer { freeifaddrs(ifaddrPointer) }

        var pointer: UnsafeMutablePointer<ifaddrs>? = firstAddr
        while let current = pointer {
            defer { pointer = current.pointee.ifa_next }
            let interface = current.pointee
            let addrFamily = interface.ifa_addr.pointee.sa_family
            guard addrFamily == UInt8(AF_INET) else { continue }

            let name = String(cString: interface.ifa_name)
            // en0/en1 = Wi-Fi/Ethernet on iOS devices; pdp_ip* are cellular,
            // deliberately excluded since this is a LAN-only discovery.
            guard name.hasPrefix("en") else { continue }

            var addr = interface.ifa_addr.pointee
            var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            let result = withUnsafePointer(to: &addr) { pointerToAddr in
                pointerToAddr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                    getnameinfo(sockaddrPointer, socklen_t(interface.ifa_addr.pointee.sa_len), &hostname, socklen_t(hostname.count), nil, 0, NI_NUMERICHOST)
                }
            }
            if result == 0 {
                address = String(cString: hostname)
                break
            }
        }
        return address
    }
}
