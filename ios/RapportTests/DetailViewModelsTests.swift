import Testing
@testable import Rapport
import Foundation

private let minimalApplicationJSON = """
{"id":1,"firma":"A","rolle":"R","main_status":"applied","is_headhunter":false,"abgesagt":false,"salary_mismatch":false}
"""

@MainActor
struct DetailViewModelsTests {
    @Test func applicationDetailViewModelAddEventReloadsAndNotifiesOnUpdate() async throws {
        let notified = Captured<Application?>(nil)
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.httpMethod == "POST" {
                let json = """
                {"id": 99, "application_id": 1, "typ": "mail", "titel": "Test", "attachments": []}
                """
                return (response, Data(json.utf8))
            }
            return (response, Data(minimalApplicationJSON.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = ApplicationDetailViewModel(api: ApplicationsAPI(client: client), applicationId: 1)
        viewModel.onUpdate = { notified.value = $0 }

        await viewModel.addEvent(typ: "mail", titel: "Test", notiz: nil, datum: nil)

        #expect(viewModel.application?.id == 1)
        #expect(notified.value?.id == 1)
    }

    @Test func contactDetailViewModelLoadsFourEventBuckets() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"calls": [], "mails": [], "messages": [], "calendar": []}
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = ContactDetailViewModel(api: ContactsAPI(client: client), contactId: 5)

        await viewModel.load()

        #expect(viewModel.events != nil)
        #expect(viewModel.errorMessage == nil)
    }

    @Test func companiesViewModelCreateInsertsAtFront() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"id": 42, "name_display": "New Co", "name_norm": "new co", "sync_status": "pending", "app_count": 0}
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = CompaniesViewModel(api: CompaniesAPI(client: client))

        let created = try await viewModel.create(name: "New Co")

        #expect(created.id == 42)
        #expect(viewModel.companies.first?.id == 42)
    }

    @Test func companyDetailViewModelLoadsById() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"id": 7, "name_display": "Acme", "name_norm": "acme", "sync_status": "done"}
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = CompanyDetailViewModel(api: CompaniesAPI(client: client), companyId: 7)

        await viewModel.load()

        #expect(viewModel.company?.id == 7)
    }

    @Test func reviewViewModelApproveRemovesItemFromList() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            if request.url!.path.hasSuffix("/approve") {
                return (response, Data(#"{"status": "approved", "event_id": 5}"#.utf8))
            }
            let json = """
            [{"id": 1, "source": "gmail", "confidence": 90, "status_only": false}]
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = ReviewViewModel(api: ReviewAPI(client: client))
        await viewModel.load()
        #expect(viewModel.items.count == 1)

        await viewModel.approve(viewModel.items[0])

        #expect(viewModel.items.isEmpty)
    }

    @Test func auditLogViewModelLoadsTotalAndEntries() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {"total": 1, "items": [{"id": 1, "action": "update", "source": "gmail"}]}
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = AuditLogViewModel(api: AuditLogAPI(client: client))

        await viewModel.load()

        #expect(viewModel.total == 1)
        #expect(viewModel.entries.first?.action == "update")
    }
}
