import Foundation

/// Only ever installed when the app is launched with `-uiTestingMockAPI`
/// (see RapportApp.swift) — lets UI tests exercise authenticated screens
/// (Applications/Kanban/detail) against canned responses instead of a real
/// backend, without needing a separate mock HTTP server process. XCUITest
/// drives the app as its own process, so this has to live in the app's own
/// code (a test's URLProtocol registration can't reach across the process
/// boundary) — gated behind a launch argument that's never set outside
/// tests, so it carries no risk in a real run.
final class MockURLProtocol: URLProtocol {
    private struct Stub {
        let matches: (URLRequest) -> Bool
        let status: Int
        let json: String
    }

    nonisolated(unsafe) private static var stubs: [Stub] = []

    static func installDefaultUITestResponses() {
        stubs = [
            Stub(matches: { $0.httpMethod == "POST" && $0.url!.path.hasSuffix("/auth/login") },
                 status: 200, json: #"{"access_token": "mock-token", "token_type": "bearer"}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/auth/me") },
                 status: 200, json: """
                 {"id": 1, "email": "test@example.com", "email_verified": true, "ui_language": "en"}
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/applications") },
                 status: 200, json: """
                 [
                   {"id": 1, "firma": "Contoso", "rolle": "iOS Engineer", "main_status": "applied", "is_headhunter": false, "abgesagt": false, "ghosting": false, "salary_mismatch": false},
                   {"id": 2, "firma": "Globex", "rolle": "Backend Engineer", "main_status": "hr", "is_headhunter": false, "abgesagt": false, "ghosting": false, "salary_mismatch": false}
                 ]
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/applications/1") },
                 status: 200, json: """
                 {"id": 1, "firma": "Contoso", "rolle": "iOS Engineer", "main_status": "applied", "is_headhunter": false, "abgesagt": false, "salary_mismatch": false}
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/contacts") },
                 status: 200, json: "[]"),
            Stub(matches: { $0.httpMethod == "GET" && ($0.url!.path.hasSuffix("/companies")) },
                 status: 200, json: "[]"),
        ]
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let stub = Self.stubs.first(where: { $0.matches(request) }) else {
            let response = HTTPURLResponse(url: request.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(#"{"detail": "no mock stub for this request"}"#.utf8))
            client?.urlProtocolDidFinishLoading(self)
            return
        }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: stub.status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(stub.json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
