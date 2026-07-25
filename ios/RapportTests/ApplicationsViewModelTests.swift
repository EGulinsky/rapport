import Testing
@testable import Rapport
import Foundation

@MainActor
struct ApplicationsViewModelTests {
    @Test func groupsApplicationsByMainStatus() async throws {
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = ApplicationsViewModel(api: ApplicationsAPI(client: client))

        // Exercise the grouping logic through the same `applications(in:)`
        // API the view uses, backed by a controlled list() response.
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            [
              {"id":1,"firma":"A","rolle":"R","main_status":"applied","is_headhunter":false,"abgesagt":false,"ghosting":false,"salary_mismatch":false},
              {"id":2,"firma":"B","rolle":"R","main_status":"hr","is_headhunter":false,"abgesagt":false,"ghosting":false,"salary_mismatch":false},
              {"id":3,"firma":"C","rolle":"R","main_status":"applied","is_headhunter":false,"abgesagt":false,"ghosting":false,"salary_mismatch":false}
            ]
            """
            return (response, Data(json.utf8))
        }
        await viewModel.load()

        #expect(viewModel.applications(in: .applied).map(\.id) == [1, 3])
        #expect(viewModel.applications(in: .hr).map(\.id) == [2])
        #expect(viewModel.applications(in: .signed).isEmpty)
    }

    @Test func updateStatusRollsBackOnFailure() async throws {
        URLProtocolStub.requestHandler = { request in
            // NB: URL.path strips the trailing slash even when .absoluteString
            // keeps it, so the list endpoint's path ends in "applications"
            // (no slash) even though the request path we asked for was "/applications/".
            if request.url!.path.hasSuffix("/applications") {
                let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
                let json = """
                [{"id":1,"firma":"A","rolle":"R","main_status":"applied","is_headhunter":false,"abgesagt":false,"ghosting":false,"salary_mismatch":false}]
                """
                return (response, Data(json.utf8))
            }
            // The PATCH to /applications/1 fails.
            let response = HTTPURLResponse(url: request.url!, statusCode: 500, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"detail": "boom"}"#.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = ApplicationsViewModel(api: ApplicationsAPI(client: client))
        await viewModel.load()
        #expect(viewModel.applications.first?.mainStatus == .applied)

        await viewModel.updateStatus(viewModel.applications[0], to: .signed)

        // Failed PATCH rolls the optimistic update back to the original status.
        #expect(viewModel.applications.first?.mainStatus == .applied)
        #expect(viewModel.errorMessage != nil)
    }
}
