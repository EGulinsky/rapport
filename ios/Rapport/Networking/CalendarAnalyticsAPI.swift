import Foundation

/// Wraps calendar.py's single endpoint (prefix "/api/calendar").
struct CalendarAPI {
    let client: APIClient

    func events(from: String? = nil, to: String? = nil) async throws -> [CalendarEventItem] {
        try await client.request("/calendar/events", query: ["from_date": from, "to_date": to])
    }
}

/// Wraps analytics.py's single endpoint (prefix "/api/analytics").
struct AnalyticsAPI {
    let client: APIClient

    func summary() async throws -> AnalyticsSummary {
        try await client.request("/analytics/summary")
    }
}
