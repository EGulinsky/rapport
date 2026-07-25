import Testing
@testable import Rapport
import Foundation

struct CalendarAnalyticsTests {
    /// A representative payload matching analytics.py's GET /api/analytics/summary
    /// exactly, including the umlaut field names ("gespräch", "gespräch_rate")
    /// that are the main risk area for this decode.
    private let summaryJSON = """
    {
      "kpis": {
        "total": 42, "active": 10, "rejected": 20, "signed": 2,
        "ghosting_count": 3, "ghosting_rate": 0.15,
        "hh_count": 5, "direct_count": 37, "hh_pct": 0.12,
        "conversion_gespräch": 0.4, "conversion_offer": 0.1,
        "avg_days_to_gespräch": 12.5, "avg_days_applied_to_rejected": 30.0
      },
      "funnel": [{"status": "applied", "label": "Applied", "count": 10, "pct": 1.0}],
      "by_month": [{"month": "2026-07", "label": "Jul 2026", "count": 5}],
      "by_source": [{"source": "LinkedIn", "count": 8}],
      "hh_vs_direct": {
        "hh": {"total": 5, "gespräch": 2, "offer": 1},
        "direct": {"total": 37, "gespräch": 10, "offer": 3}
      },
      "rejection_by_status": [{"status": "hr", "label": "HR", "count": 4}],
      "company_sync": {"total": 20, "pending": 2, "done": 15, "failed": 3},
      "stage_conversions": [
        {"from_status": "applied", "from_label": "Applied", "to_status": "hr", "to_label": "HR", "rate": 0.5, "drop_off": 5}
      ],
      "bottleneck": null,
      "by_company_type": [{"label": "Startup", "total": 10, "gespräch": 4, "offer": 1, "gespräch_rate": 0.4, "offer_rate": 0.1}],
      "by_employee_range": [],
      "by_role_category": []
    }
    """

    @Test func decodesAnalyticsSummaryWithUmlautFieldNames() throws {
        let summary = try APIClient.decoder.decode(AnalyticsSummary.self, from: Data(summaryJSON.utf8))
        #expect(summary.kpis.total == 42)
        #expect(summary.kpis.conversionGespräch == 0.4)
        #expect(summary.kpis.avgDaysToGespräch == 12.5)
        #expect(summary.hhVsDirect.hh.gespräch == 2)
        #expect(summary.byCompanyType.first?.gesprächRate == 0.4)
        #expect(summary.bottleneck == nil)
        #expect(summary.stageConversions.first?.fromStatus == "applied")
    }

    @MainActor
    @Test func calendarViewModelGroupsEventsByDayInAscendingOrder() async throws {
        URLProtocolStub.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            let json = """
            [
              {"id":1,"application_id":1,"firma":"A","rolle":"R","main_status":"hr","typ":"gespräch","datum":"2026-08-02"},
              {"id":2,"application_id":2,"firma":"B","rolle":"R","main_status":"hr","typ":"gespräch","datum":"2026-07-30"},
              {"id":3,"application_id":1,"firma":"A","rolle":"R","main_status":"hr","typ":"gespräch","datum":"2026-08-02"}
            ]
            """
            return (response, Data(json.utf8))
        }
        let client = APIClient(session: URLProtocolStub.makeSession())
        await client.updateBaseURL(URL(string: "http://localhost:8000"))
        let viewModel = CalendarViewModel(api: CalendarAPI(client: client))

        await viewModel.load()

        let groups = viewModel.eventsByDay
        #expect(groups.map(\.day) == ["2026-07-30", "2026-08-02"])
        #expect(groups.last?.events.count == 2)
    }
}
