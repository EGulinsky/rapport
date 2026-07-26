import Foundation
import Observation

@MainActor
@Observable
final class ServerDiscoveryViewModel {
    private(set) var isScanning = false
    private(set) var discoveredServers: [DiscoveredServer] = []
    private(set) var errorMessage: String?
    private(set) var hasScanned = false

    func scan() async {
        guard !isScanning else { return }
        isScanning = true
        errorMessage = nil
        defer {
            isScanning = false
            hasScanned = true
        }

        guard let subnet = ServerDiscovery.currentSubnetPrefix() else {
            errorMessage = "Couldn't determine the local network — make sure Wi-Fi is on."
            discoveredServers = []
            return
        }
        discoveredServers = await ServerDiscovery.scan(subnet: subnet)
        if discoveredServers.isEmpty {
            errorMessage = "No Rapport server found on this network."
        }
    }
}
