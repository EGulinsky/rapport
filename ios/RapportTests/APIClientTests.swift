import Testing
@testable import Rapport
import Foundation

/// Boxes a value captured inside URLProtocolStub's @Sendable request handler.
/// Test-only, single-writer-then-single-reader usage — safe despite @unchecked.
/// Not marked `private` so other test files in this target can reuse it.
final class Captured<T>: @unchecked Sendable {
    var value: T
    init(_ value: T) { self.value = value }
}

struct APIClientTests {
    private struct Echo: Decodable, Equatable {
        let emailVerified: Bool
        let uiLanguage: String
    }

    @Test func joinsBaseURLAndApiPrefixAndPath() async throws {
        let capturedURL = Captured<URL?>(nil)
        URLProtocolStub.requestHandler = { request in
            capturedURL.value = request.url
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"email_verified": true, "ui_language": "en"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://192.168.1.50:8000"))

        let _: Echo = try await client.request("/auth/me")

        #expect(capturedURL.value?.absoluteString == "http://192.168.1.50:8000/api/auth/me")
    }

    @Test func setsAuthorizationHeaderWhenTokenPresent() async throws {
        let capturedAuth = Captured<String?>(nil)
        URLProtocolStub.requestHandler = { request in
            capturedAuth.value = request.value(forHTTPHeaderField: "Authorization")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"email_verified": true, "ui_language": "en"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://192.168.1.50:8000"))
        await client.updateToken("test-jwt")

        let _: Echo = try await client.request("/auth/me")

        #expect(capturedAuth.value == "Bearer test-jwt")
    }

    @Test func omitsAuthorizationHeaderWhenNoToken() async throws {
        let capturedAuth = Captured<String?>("unset")
        URLProtocolStub.requestHandler = { request in
            capturedAuth.value = request.value(forHTTPHeaderField: "Authorization")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"email_verified": true, "ui_language": "en"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://192.168.1.50:8000"))

        let _: Echo = try await client.request("/auth/me")

        #expect(capturedAuth.value == nil)
    }

    @Test func throwsNotConfiguredWithoutBaseURL() async throws {
        let client = APIClient(session: URLProtocolStub.makeSession())
        await #expect(throws: APIError.self) {
            let _: Echo = try await client.request("/auth/me")
        }
    }

    @Test func throwsAPIErrorOnNon2xxResponse() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!
            let body = #"{"detail": {"error_key": "auth.login_failed", "message": "wrong"}}"#
            return (response, Data(body.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://192.168.1.50:8000"))

        do {
            let _: Echo = try await client.request("/auth/me")
            Issue.record("expected request to throw")
        } catch let error as APIError {
            #expect(error.errorKey == "auth.login_failed")
            #expect(error.statusCode == 401)
        }
    }

    @Test func encodesRequestBodyWithSnakeCaseKeys() async throws {
        let capturedBody = Captured<[String: Any]?>(nil)
        URLProtocolStub.requestHandler = { request in
            if let bodyData = request.httpBody ?? request.httpBodyStream.map({ stream -> Data in
                stream.open()
                defer { stream.close() }
                var data = Data()
                let bufferSize = 1024
                var buffer = [UInt8](repeating: 0, count: bufferSize)
                while stream.hasBytesAvailable {
                    let read = stream.read(&buffer, maxLength: bufferSize)
                    if read > 0 { data.append(buffer, count: read) }
                }
                return data
            }) {
                capturedBody.value = try? JSONSerialization.jsonObject(with: bodyData) as? [String: Any]
            }
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"email_verified": true, "ui_language": "en"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://192.168.1.50:8000"))

        let _: Echo = try await client.request(
            "/auth/login", method: .post,
            body: LoginPayload(email: "a@b.com", password: "secret123")
        )

        #expect(capturedBody.value?["email"] as? String == "a@b.com")
        #expect(capturedBody.value?["password"] as? String == "secret123")
    }
}
