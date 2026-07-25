import Foundation

/// Wraps backend/app/routers/companies.py's endpoints (prefix "/api/companies",
/// note: no trailing slash on the collection routes, unlike applications/contacts).
struct CompaniesAPI {
    let client: APIClient

    func list(search: String? = nil, sort: String = "name", order: String = "asc") async throws -> [CompanyProfile] {
        try await client.request("/companies", query: ["search": search, "sort": sort, "order": order])
    }

    func get(_ id: Int) async throws -> CompanyProfile {
        try await client.request("/companies/\(id)")
    }

    func create(name: String) async throws -> CompanyProfile {
        try await client.request("/companies", method: .post, body: CompanyCreatePayload(name: name))
    }

    func update(_ id: Int, _ payload: CompanyUpdatePayload) async throws -> CompanyProfile {
        try await client.request("/companies/\(id)", method: .patch, body: payload)
    }

    func assignContact(companyId: Int, contactId: Int) async throws {
        try await client.requestVoid("/companies/\(companyId)/contacts/\(contactId)", method: .post)
    }

    func unassignContact(companyId: Int, contactId: Int) async throws {
        try await client.requestVoid("/companies/\(companyId)/contacts/\(contactId)", method: .delete)
    }

    func bulkDelete(_ ids: [Int]) async throws {
        struct Body: Encodable { let ids: [Int] }
        try await client.requestVoid("/companies/bulk", method: .delete, body: Body(ids: ids))
    }
}
