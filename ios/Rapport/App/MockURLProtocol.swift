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
                 status: 200, json: """
                 [{"id": 1, "name": "Lovelace", "vorname": "Ada", "firma": "Contoso", "rolle": "Recruiter", "phones": []}]
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/companies") },
                 status: 200, json: """
                 [{"id": 1, "name_display": "Contoso", "name_norm": "contoso", "sync_status": "done", "app_count": 1}]
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/calendar/events") },
                 status: 200, json: "[]"),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/analytics/summary") },
                 status: 200, json: """
                 {
                   "kpis": {
                     "total": 2, "active": 2, "rejected": 0, "signed": 0,
                     "ghosting_count": 0, "ghosting_rate": 0.0,
                     "hh_count": 0, "direct_count": 2, "hh_pct": 0.0,
                     "conversion_gespräch": 0.0, "conversion_offer": 0.0,
                     "avg_days_to_gespräch": 0.0, "avg_days_applied_to_rejected": 0.0
                   },
                   "funnel": [{"status": "applied", "label": "Applied", "count": 2, "pct": 1.0}],
                   "by_month": [], "by_source": [],
                   "hh_vs_direct": {"hh": {"total": 0, "gespräch": 0, "offer": 0}, "direct": {"total": 2, "gespräch": 0, "offer": 0}},
                   "rejection_by_status": [], "company_sync": {"total": 1, "pending": 0, "done": 1, "failed": 0},
                   "stage_conversions": [], "bottleneck": null,
                   "by_company_type": [], "by_employee_range": [], "by_role_category": []
                 }
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/review") },
                 status: 200, json: """
                 [{"id": 1, "source": "gmail", "confidence": 80, "titel": "Interview invite", "status_only": false}]
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/audit") },
                 status: 200, json: """
                 {"total": 1, "items": [{"id": 1, "action": "update", "source": "gmail", "app_firma": "Contoso", "field": "main_status", "old_value": "applied", "new_value": "hr"}]}
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/settings/sync") },
                 status: 200, json: """
                 {"google_enabled": true, "gmail_enabled": true, "gcal_enabled": true,
                  "icloud_enabled": true, "icloud_mail_enabled": true, "icloud_cal_enabled": true,
                  "icloud_notes_enabled": true, "icloud_reminders_enabled": true, "icloud_contacts_enabled": true,
                  "icloud_calls_enabled": true, "linkedin_enabled": true, "files_enabled": true, "audit_log_level": "normal"}
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/settings/ai") },
                 status: 200, json: #"{"provider": "openai", "model": "gpt-4o-mini", "has_key": false, "enabled": true}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/settings/maps") },
                 status: 200, json: #"{"has_key": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/settings/logo") },
                 status: 200, json: #"{"api_key": null}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/settings/agent") },
                 status: 200, json: #"{"url": null, "has_token": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/settings/agent/health") },
                 status: 200, json: #"{"reachable": false, "modules": {}}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/backup/status") },
                 status: 200, json: """
                 {"enabled": false, "backup_folder": null, "frequency_hours": 24, "keep_count": 7, "keep_daily": 14, "keep_weekly": 8, "last_backup": null}
                 """),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/google/status") },
                 status: 200, json: #"{"connected": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/icloud/status") },
                 status: 200, json: #"{"connected": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/icloud/calls/status") },
                 status: 200, json: #"{"enabled": false, "bridge_reachable": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/files/status") },
                 status: 200, json: #"{"enabled": false, "folder_path": null, "bridge_reachable": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/linkedin/config") },
                 status: 200, json: #"{"configured": false, "has_session": false}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/linkedin/messages/status") },
                 status: 200, json: #"{"conversation_count": 0}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/company/status") },
                 status: 200, json: #"{"running": false, "pending": 0, "done": 1, "failed": 0, "needs_review": 0, "profiles": []}"#),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/google/progress") },
                 status: 200, json: "{}"),
            Stub(matches: { $0.httpMethod == "GET" && $0.url!.path.hasSuffix("/sync/google/batch/results") },
                 status: 200, json: "{}"),
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
