import Foundation

/// Mirrors calendar.py's CalendarEvent (GET /api/calendar/events).
struct CalendarEventItem: Codable, Identifiable, Equatable {
    let id: Int
    var applicationId: Int
    var firma: String
    var rolle: String
    var mainStatus: String
    var typ: String
    var datum: String
    var titel: String?
    var notiz: String?
    var autor: String?
    var source: String?
}
