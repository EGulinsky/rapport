import Testing
@testable import Rapport
import Foundation

struct ApplicationModelTests {
    /// A representative payload matching backend/app/schemas.py's
    /// ApplicationListItem shape exactly (GET /api/applications/ item).
    private let listItemJSON = """
    {
      "id": 42, "firma": "Contoso AG", "rolle": "Backend Engineer",
      "main_status": "hr", "sub_status": "1_scheduled", "is_headhunter": false,
      "abgesagt": false, "ghosting": false, "salary_mismatch": true,
      "salary_currency": "EUR", "salary_expectation_min": 70000,
      "naechster_schritt": "Interview am 2026-08-01", "kommentar": "Sehr interessant"
    }
    """

    @Test func decodesApplicationListItemShape() throws {
        let app = try APIClient.decoder.decode(Application.self, from: Data(listItemJSON.utf8))
        #expect(app.id == 42)
        #expect(app.firma == "Contoso AG")
        #expect(app.mainStatus == .hr)
        #expect(app.subStatus == "1_scheduled")
        #expect(app.salaryMismatch == true)
        #expect(app.salaryExpectationMin == 70000)
        #expect(app.naechsterSchritt == "Interview am 2026-08-01")
        // Fields only present on ApplicationRead are absent from this payload shape.
        #expect(app.contacts == nil)
        #expect(app.events == nil)
    }

    /// A representative payload matching ApplicationRead (GET /api/applications/{id}),
    /// including nested contacts/events.
    private let detailJSON = """
    {
      "id": 42, "firma": "Contoso AG", "rolle": "Backend Engineer",
      "main_status": "hr", "is_headhunter": true, "zielfirma_bei_hh": "Contoso AG",
      "abgesagt": false, "salary_mismatch": false,
      "contacts": [
        {"id": 7, "name": "Musterfrau", "vorname": "Erika", "phones": [{"id": 1, "number": "0151 234", "type": "mobile"}]}
      ],
      "events": [
        {"id": 100, "application_id": 42, "typ": "gespräch", "datum": "2026-07-20", "attachments": []}
      ]
    }
    """

    @Test func decodesApplicationReadShapeWithNestedContactsAndEvents() throws {
        let app = try APIClient.decoder.decode(Application.self, from: Data(detailJSON.utf8))
        #expect(app.isHeadhunter == true)
        #expect(app.zielfirmaBeiHh == "Contoso AG")
        #expect(app.contacts?.count == 1)
        #expect(app.contacts?.first?.displayName == "Erika Musterfrau")
        #expect(app.contacts?.first?.phones.first?.number == "0151 234")
        #expect(app.events?.count == 1)
        #expect(app.events?.first?.typ == "gespräch")
    }

    @Test func contactDisplayNameFallsBackToBareNameWithoutVorname() {
        let contact = Contact(id: 1, name: "Zoch", vorname: nil, email: nil, phones: [], linkedinUrl: nil, firma: nil, rolle: nil, typ: nil, notizen: nil, letzterKontakt: nil, icloudLastSyncedAt: nil, createdAt: nil, applications: nil, companyWebsite: nil, companyProfileId: nil)
        #expect(contact.displayName == "Zoch")
    }

    @Test func encodesApplicationUpdatePayloadOmittingNilFields() throws {
        let payload = ApplicationUpdatePayload(mainStatus: "signed")
        let data = try APIClient.encoder.encode(payload)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(json?["main_status"] as? String == "signed")
        #expect(json?["firma"] == nil)
        #expect(json?["rolle"] == nil)
    }
}
