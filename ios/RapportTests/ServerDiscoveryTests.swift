import Testing
@testable import Rapport
import Foundation

struct ServerDiscoveryTests {
    @Test func candidateHostsCoversFullUsableRangeOfA24() {
        let hosts = ServerDiscovery.candidateHosts(subnet: "192.168.1")

        #expect(hosts.count == 254)
        #expect(hosts.first == "192.168.1.1")
        #expect(hosts.last == "192.168.1.254")
        #expect(!hosts.contains("192.168.1.0"))   // network address, not a usable host
        #expect(!hosts.contains("192.168.1.255")) // broadcast address, not a usable host
    }

    @Test func discoveredServerBuildsCorrectBaseURL() {
        let server = DiscoveredServer(host: "192.168.1.50", port: 8000)

        #expect(server.baseURLString == "http://192.168.1.50:8000")
        #expect(server.id == "192.168.1.50:8000")
    }

    @Test func subnetPrefixExtractsFirstThreeOctets() {
        #expect(ServerDiscovery.subnetPrefix(fromIPv4Address: "192.168.1.42") == "192.168.1")
        #expect(ServerDiscovery.subnetPrefix(fromIPv4Address: "10.0.0.5") == "10.0.0")
    }

    @Test func subnetPrefixRejectsMalformedAddresses() {
        #expect(ServerDiscovery.subnetPrefix(fromIPv4Address: "not-an-ip") == nil)
        #expect(ServerDiscovery.subnetPrefix(fromIPv4Address: "192.168.1") == nil)
        #expect(ServerDiscovery.subnetPrefix(fromIPv4Address: "") == nil)
    }
}
