import Testing
@testable import Rapport
import Foundation

private let oneCandidateJSON = """
[{"id": 5, "source": "gmail", "confidence": 60, "titel": "Re: Interview", "suggested_app_id": 1}]
"""

@MainActor
struct ManualSyncViewModelTests {
    private func makeViewModel(handler: @escaping @Sendable (URLRequest) throws -> (HTTPURLResponse, Data)) async -> ManualSyncViewModel {
        URLProtocolStub.requestHandler = handler
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        return ManualSyncViewModel(api: TargetedSyncAPI(client: client), applicationId: 1)
    }

    @Test func loadCandidatesDecodesList() async throws {
        let viewModel = await makeViewModel { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(oneCandidateJSON.utf8))
        }

        await viewModel.loadCandidates()

        #expect(viewModel.candidates.count == 1)
        #expect(viewModel.candidates.first?.titel == "Re: Interview")
    }

    @Test func assignWithoutConflictRemovesCandidateFromList() async throws {
        let viewModel = await makeViewModel { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.httpMethod == "GET" {
                return (response, Data(oneCandidateJSON.utf8))
            }
            return (response, Data(#"{"conflict": false, "event_id": 42}"#.utf8))
        }
        await viewModel.loadCandidates()
        let candidate = try #require(viewModel.candidates.first)

        let result = await viewModel.assign(candidate)

        #expect(result?.eventId == 42)
        #expect(viewModel.candidates.isEmpty)
        #expect(viewModel.pendingConflict == nil)
    }

    @Test func assignWithConflictSetsPendingConflictAndKeepsCandidate() async throws {
        let viewModel = await makeViewModel { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.httpMethod == "GET" {
                return (response, Data(oneCandidateJSON.utf8))
            }
            let json = """
            {"conflict": true, "conflict_app_id": 9, "conflict_app_firma": "Other Co", "conflict_event_id": 7}
            """
            return (response, Data(json.utf8))
        }
        await viewModel.loadCandidates()
        let candidate = try #require(viewModel.candidates.first)

        _ = await viewModel.assign(candidate)

        #expect(viewModel.candidates.count == 1) // not removed — still pending a decision
        #expect(viewModel.pendingConflict?.result.conflictAppFirma == "Other Co")
    }

    @Test func confirmPendingConflictReassignsAndRemovesCandidate() async throws {
        let callCount = Captured<Int>(0)
        let viewModel = await makeViewModel { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.httpMethod == "GET" {
                return (response, Data(oneCandidateJSON.utf8))
            }
            callCount.value += 1
            if callCount.value == 1 {
                return (response, Data(#"{"conflict": true, "conflict_app_id": 9, "conflict_app_firma": "Other Co", "conflict_event_id": 7}"#.utf8))
            }
            // Second assign call carries removeFromOther:true and now succeeds.
            return (response, Data(#"{"conflict": false, "event_id": 42}"#.utf8))
        }
        await viewModel.loadCandidates()
        let candidate = try #require(viewModel.candidates.first)
        _ = await viewModel.assign(candidate)
        #expect(viewModel.pendingConflict != nil)

        await viewModel.confirmPendingConflict()

        #expect(viewModel.pendingConflict == nil)
        #expect(viewModel.candidates.isEmpty)
    }
}

@MainActor
struct CompanySyncViewModelTests {
    @Test func loadDecodesStatusWithProfiles() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {
              "running": false, "current_company": null, "pending": 2, "done": 5, "failed": 1, "needs_review": 0,
              "profiles": [{"id": 1, "name_display": "Acme", "sync_status": "done"}]
            }
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = CompanySyncViewModel(api: CompanySyncAPI(client: client))

        await viewModel.load()

        #expect(viewModel.status?.pending == 2)
        #expect(viewModel.status?.profiles.first?.nameDisplay == "Acme")
    }
}

struct BackupPickerAPITests {
    @Test func pickFolderReturnsPathFromResponse() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"path": "/Users/test/Backups"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = BackupAPI(client: client)

        let path = try await api.pickFolder()

        #expect(path == "/Users/test/Backups")
    }

    @Test func restoreFileSendsPathAndDecodesResult() async throws {
        let captured = Captured<Data?>(nil)
        URLProtocolStub.requestHandler = { request in
            captured.value = request.httpBodyStreamData() ?? request.httpBody
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"success": true, "filename": "backup-2.db"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = BackupAPI(client: client)

        let result = try await api.restoreFile(path: "/Users/test/Backups/backup-2.db")

        #expect(result.success == true)
        let body = try #require(captured.value)
        let object = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        #expect(object?["path"] as? String == "/Users/test/Backups/backup-2.db")
    }
}
