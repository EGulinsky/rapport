import Foundation
import Observation

@MainActor
@Observable
final class ApplicationDetailViewModel {
    private let api: ApplicationsAPI
    let applicationId: Int
    /// Notified with the fresh Application whenever it's reloaded, so the
    /// owning list/board (a different view model's array) can stay in sync
    /// without this view model knowing about ApplicationsViewModel directly.
    var onUpdate: ((Application) -> Void)?

    private(set) var application: Application?
    var isLoading = false
    var errorMessage: String?

    init(api: ApplicationsAPI, applicationId: Int) {
        self.api = api
        self.applicationId = applicationId
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let app = try await api.get(applicationId)
            application = app
            onUpdate?(app)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func update(_ payload: ApplicationUpdatePayload) async {
        do {
            let updated = try await api.update(applicationId, payload)
            application = updated
            onUpdate?(updated)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func addEvent(typ: String, titel: String?, notiz: String?, datum: Date?) async {
        let datumString = datum.map { DateFormatter.iso8601DateOnly.string(from: $0) }
        let payload = EventCreatePayload(applicationId: applicationId, typ: typ, datum: datumString, titel: titel, notiz: notiz, autor: nil, source: nil)
        do {
            _ = try await api.addEvent(applicationId, payload)
            await load()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteEvent(_ event: Event) async {
        do {
            try await api.deleteEvent(applicationId, event.id)
            await load()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func addContact(name: String, email: String, rolle: String?) async {
        let payload = ContactCreatePayload(name: name, vorname: nil, email: email, phones: [], linkedinUrl: nil, firma: application?.firma, rolle: rolle, typ: nil, notizen: nil, applicationId: applicationId)
        do {
            _ = try await api.addContact(applicationId, payload)
            await load()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func removeContact(_ contact: Contact) async {
        do {
            try await api.deleteContact(applicationId, contact.id)
            await load()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func requestAIAssessment() async {
        do {
            try await api.aiAssess(applicationId)
            await load()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

extension DateFormatter {
    static let iso8601DateOnly: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()
}
