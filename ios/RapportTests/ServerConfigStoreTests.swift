import Testing
@testable import Rapport
import Foundation

@MainActor
struct ServerConfigStoreTests {
    private func freshStore() -> ServerConfigStore {
        let suiteName = "ServerConfigStoreTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        return ServerConfigStore(defaults: defaults)
    }

    @Test func normalizeAddsHttpSchemeWhenMissing() {
        let url = ServerConfigStore.normalize("192.168.1.50:8000")
        #expect(url?.absoluteString == "http://192.168.1.50:8000")
    }

    @Test func normalizePreservesExplicitScheme() {
        let url = ServerConfigStore.normalize("https://rapport.example.com")
        #expect(url?.absoluteString == "https://rapport.example.com")
    }

    @Test func normalizeStripsTrailingSlash() {
        let url = ServerConfigStore.normalize("http://192.168.1.50:8000/")
        #expect(url?.absoluteString == "http://192.168.1.50:8000")
    }

    @Test func normalizeRejectsBlankInput() {
        #expect(ServerConfigStore.normalize("   ") == nil)
    }

    @Test func baseURLRoundTripsThroughStorage() {
        let store = freshStore()
        #expect(store.baseURL == nil)
        store.baseURL = URL(string: "http://192.168.1.50:8000")
        #expect(store.baseURL?.absoluteString == "http://192.168.1.50:8000")
        store.clear()
        #expect(store.baseURL == nil)
    }
}
