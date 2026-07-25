import Foundation
import Observation

@MainActor
@Observable
final class ContactDetailViewModel {
    private let api: ContactsAPI
    let contactId: Int

    private(set) var events: ContactEvents?
    var isLoading = false
    var errorMessage: String?

    init(api: ContactsAPI, contactId: Int) {
        self.api = api
        self.contactId = contactId
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            events = try await api.events(contactId)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
