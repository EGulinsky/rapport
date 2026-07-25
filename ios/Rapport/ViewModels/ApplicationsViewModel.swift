import Foundation
import Observation

/// Owns the application list + its filters/search, shared between the
/// Kanban board and the table/list view (both are just different
/// presentations of the same underlying data — mirrors App.tsx's single
/// `applications` state feeding both ApplicationTable and KanbanBoard).
@MainActor
@Observable
final class ApplicationsViewModel {
    private let api: ApplicationsAPI

    private(set) var applications: [Application] = []
    var isLoading = false
    var errorMessage: String?

    var searchText = ""
    var showRejected = false

    init(api: ApplicationsAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            applications = try await api.list(
                search: searchText.isEmpty ? nil : searchText,
                showRejected: showRejected
            )
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Applications grouped by main status, in MainStatus.pipeline order —
    /// feeds the Kanban board's columns. Rejected applications are excluded
    /// here regardless of `showRejected` (the board never shows a Rejected
    /// column; the toggle only affects whether they're fetched at all,
    /// matching KanbanBoard.tsx).
    func applications(in status: MainStatus) -> [Application] {
        applications.filter { $0.mainStatus == status }
    }

    /// Moves a card to a new column (drag-and-drop on the Kanban board, or a
    /// manual status change from the detail view). Resets sub_status when
    /// leaving hr/fb, matching KanbanBoard.tsx's drag handler — a leftover
    /// "2nd interview scheduled" sub-status makes no sense once the card is
    /// back in e.g. Applied.
    func updateStatus(_ application: Application, to newStatus: MainStatus) async {
        guard let index = applications.firstIndex(where: { $0.id == application.id }) else { return }
        let previous = applications[index]
        let clearsSubStatus = ![MainStatus.hr, .fb].contains(newStatus)

        // Optimistic update so the drag feels instant; rolled back on failure.
        applications[index].mainStatus = newStatus
        if clearsSubStatus { applications[index].subStatus = nil }

        do {
            let payload = ApplicationUpdatePayload(mainStatus: newStatus.rawValue, subStatus: clearsSubStatus ? nil : previous.subStatus)
            let updated = try await api.update(application.id, payload)
            applications[index] = updated
        } catch let error as APIError {
            applications[index] = previous
            errorMessage = error.message
        } catch {
            applications[index] = previous
            errorMessage = error.localizedDescription
        }
    }

    func create(_ payload: ApplicationCreatePayload) async throws -> Application {
        let created = try await api.create(payload)
        applications.insert(created, at: 0)
        return created
    }

    func delete(_ application: Application) async {
        do {
            try await api.delete(application.id)
            applications.removeAll { $0.id == application.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Refreshes a single application in place after its detail view saves a
    /// change (event added, contact linked, etc.) — avoids a full list reload.
    func replace(_ application: Application) {
        if let index = applications.firstIndex(where: { $0.id == application.id }) {
            applications[index] = application
        }
    }
}
