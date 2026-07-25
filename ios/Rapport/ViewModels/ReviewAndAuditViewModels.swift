import Foundation
import Observation

@MainActor
@Observable
final class ReviewViewModel {
    private let api: ReviewAPI

    private(set) var items: [PendingMatchRead] = []
    var isLoading = false
    var errorMessage: String?

    init(api: ReviewAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            items = try await api.list()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func approve(_ item: PendingMatchRead) async {
        do {
            _ = try await api.approve(matchId: item.id, payload: ApproveMatchPayload(
                applicationId: item.suggestedAppId,
                eventType: item.eventType,
                datum: item.datum,
                titel: item.titel,
                linkedinUrl: nil
            ))
            items.removeAll { $0.id == item.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func reject(_ item: PendingMatchRead) async {
        do {
            _ = try await api.reject(matchId: item.id)
            items.removeAll { $0.id == item.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
@Observable
final class AuditLogViewModel {
    private let api: AuditLogAPI

    private(set) var entries: [AuditLogEntry] = []
    private(set) var total = 0
    var isLoading = false
    var errorMessage: String?
    var entityTypeFilter: String?

    init(api: AuditLogAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response = try await api.list(entityType: entityTypeFilter)
            entries = response.items
            total = response.total
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
