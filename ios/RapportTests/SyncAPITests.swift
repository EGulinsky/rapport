import Testing
@testable import Rapport
import Foundation

struct SyncAPITests {
    @Test func syncProgressRequestsGoogleProgressPathRegardlessOfSource() async throws {
        let captured = Captured<URL?>(nil)
        URLProtocolStub.requestHandler = { request in
            captured.value = request.url
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"gmail": {"label":"Gmail","step":"Done","current":10,"total":10,"percent":100,"done":true,"created":3,"updated":0,"skipped":7}}
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = SyncProgressAPI(client: client)

        let progress = try await api.progress()

        #expect(captured.value?.absoluteString.hasSuffix("/sync/google/progress") == true)
        #expect(progress["gmail"]?.created == 3)
        #expect(progress["gmail"]?.skipped == 7)
    }

    @Test func companySyncRunEncodesForceAndCompanyIdsAsQueryParams() async throws {
        let captured = Captured<URL?>(nil)
        URLProtocolStub.requestHandler = { request in
            captured.value = request.url
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("""
            {"started": true, "count": 2}
            """.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = CompanySyncAPI(client: client)

        _ = try await api.run(force: true, companyIds: [1, 2])

        let query = captured.value?.query ?? ""
        #expect(query.contains("force=true"))
        #expect(query.contains("company_ids=1,2"))
    }

    @Test func backupRestoreSendsFilenameAndFolderInBody() async throws {
        let captured = Captured<Data?>(nil)
        URLProtocolStub.requestHandler = { request in
            captured.value = request.httpBodyStreamData() ?? request.httpBody
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("""
            {"success": true, "filename": "backup-1.db"}
            """.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = BackupAPI(client: client)

        let result = try await api.restore(filename: "backup-1.db", folder: "/backups")

        #expect(result.success == true)
        let body = try #require(captured.value)
        let object = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        #expect(object?["filename"] as? String == "backup-1.db")
        #expect(object?["folder"] as? String == "/backups")
    }
}

private extension URLRequest {
    /// URLProtocol-intercepted requests carry the body via `httpBodyStream`
    /// rather than `httpBody` in some URLSession configurations — read
    /// through the stream if the plain property is empty.
    func httpBodyStreamData() -> Data? {
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: bufferSize)
            if read > 0 { data.append(buffer, count: read) } else { break }
        }
        return data.isEmpty ? nil : data
    }
}
