import Testing
@testable import Rapport
import Foundation

struct ContactsAndCompaniesAPITests {
    @Test func contactsListRequestsExpectedPathAndQuery() async throws {
        let capturedURL = Captured<URL?>(nil)
        URLProtocolStub.requestHandler = { request in
            capturedURL.value = request.url
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("[]".utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = ContactsAPI(client: client)

        _ = try await api.list(search: "Erika", companyProfileId: 5)

        let url = try #require(capturedURL.value)
        // NB: URL.path strips the trailing slash even though .absoluteString
        // (and what's actually sent over the wire) keeps it — see the same
        // gotcha noted in ApplicationsViewModelTests.swift.
        #expect(url.path == "/api/contacts")
        let query = url.query ?? ""
        #expect(query.contains("search=Erika"))
        #expect(query.contains("company_profile_id=5"))
    }

    @Test func contactEventsDecodesFourBuckets() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            {
              "calls": [{"id":1,"application_id":2,"typ":"notiz"}],
              "mails": [],
              "messages": [],
              "calendar": []
            }
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = ContactsAPI(client: client)

        let events = try await api.events(2)
        #expect(events.calls.count == 1)
        #expect(events.calls.first?.applicationId == 2)
        #expect(events.mails.isEmpty)
    }

    @Test func companiesListUsesNoTrailingSlash() async throws {
        let capturedURL = Captured<URL?>(nil)
        URLProtocolStub.requestHandler = { request in
            capturedURL.value = request.url
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("[]".utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let api = CompaniesAPI(client: client)

        _ = try await api.list()

        // companies.py's collection routes deliberately have no trailing
        // slash (unlike applications/contacts) -- see the API catalog.
        #expect(capturedURL.value?.path == "/api/companies")
    }

    @Test func decodesCompanyProfileDetailWithNestedContacts() throws {
        let json = """
        {
          "id": 9, "name_norm": "contoso ag", "name_display": "Contoso AG",
          "sync_status": "done",
          "contacts": [
            {"id": 3, "name": "Musterfrau", "vorname": "Erika", "phones": []}
          ]
        }
        """
        let company = try APIClient.decoder.decode(CompanyProfile.self, from: Data(json.utf8))
        #expect(company.nameDisplay == "Contoso AG")
        #expect(company.contacts?.first?.displayName == "Erika Musterfrau")
    }
}

/// Shared with APIClientTests.swift's Captured<T> box -- see that file for
/// why a plain captured var doesn't compile under Swift 6 strict concurrency.
