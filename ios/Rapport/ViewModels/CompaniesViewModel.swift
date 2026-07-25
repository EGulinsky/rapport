import Foundation
import Observation

@MainActor
@Observable
final class CompaniesViewModel {
    private let api: CompaniesAPI

    private(set) var companies: [CompanyProfile] = []
    var isLoading = false
    var errorMessage: String?
    var searchText = ""

    init(api: CompaniesAPI) {
        self.api = api
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            companies = try await api.list(search: searchText.isEmpty ? nil : searchText)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func create(name: String) async throws -> CompanyProfile {
        let created = try await api.create(name: name)
        companies.insert(created, at: 0)
        return created
    }
}

@MainActor
@Observable
final class CompanyDetailViewModel {
    private let api: CompaniesAPI
    let companyId: Int

    private(set) var company: CompanyProfile?
    var isLoading = false
    var errorMessage: String?

    init(api: CompaniesAPI, companyId: Int) {
        self.api = api
        self.companyId = companyId
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            company = try await api.get(companyId)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
