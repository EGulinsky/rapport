import Foundation

/// Intercepts every request made through a URLSession configured with this
/// protocol registered, so networking tests never touch a real server.
/// `requestHandler` is set per-test and must return (response, body).
final class URLProtocolStub: URLProtocol {
    // Test-only, single-threaded-per-test usage (Swift Testing runs each test
    // to completion before starting the next unless explicitly parallelized,
    // which this suite doesn't opt into) — safe despite not being isolated.
    nonisolated(unsafe) static var requestHandler: (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = URLProtocolStub.requestHandler else {
            fatalError("URLProtocolStub.requestHandler not set")
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}

    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLProtocolStub.self]
        return URLSession(configuration: config)
    }
}
