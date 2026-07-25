import Foundation
import Observation

@MainActor
@Observable
final class ContactsViewModel {
    private let api: ContactsAPI

    private(set) var contacts: [Contact] = []
    var isLoading = false
    var errorMessage: String?
    var searchText = ""

    init(api: ContactsAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            contacts = try await api.list(search: searchText.isEmpty ? nil : searchText)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func delete(_ contact: Contact) async {
        do {
            try await api.bulkDelete([contact.id])
            contacts.removeAll { $0.id == contact.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
