import Foundation
import Observation

@MainActor
@Observable
final class CalendarViewModel {
    private let api: CalendarAPI

    private(set) var events: [CalendarEventItem] = []
    var isLoading = false
    var errorMessage: String?

    init(api: CalendarAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            events = try await api.events()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Upcoming events grouped by day (formatted date string), in ascending
    /// order — matches how the backend already sorts them.
    var eventsByDay: [(day: String, events: [CalendarEventItem])] {
        let groups = Dictionary(grouping: events, by: \.datum)
        return groups.keys.sorted().map { day in (day: day, events: groups[day] ?? []) }
    }
}

@MainActor
@Observable
final class AnalyticsViewModel {
    private let api: AnalyticsAPI

    private(set) var summary: AnalyticsSummary?
    var isLoading = false
    var errorMessage: String?

    init(api: AnalyticsAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            summary = try await api.summary()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
