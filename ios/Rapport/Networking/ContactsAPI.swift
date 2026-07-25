import Foundation

/// Wraps backend/app/routers/contacts.py's endpoints (prefix "/api/contacts").
struct ContactsAPI {
    let client: APIClient

    func list(search: String? = nil, companyProfileId: Int? = nil) async throws -> [Contact] {
        try await client.request(
            "/contacts/",
            query: ["search": search, "company_profile_id": companyProfileId.map(String.init)]
        )
    }

    func events(_ contactId: Int) async throws -> ContactEvents {
        try await client.request("/contacts/\(contactId)/events")
    }

    /// Response is a raw dict {id, name, firma, company_profile_id} per the
    /// API catalog — only `id` is needed to refresh the list afterward.
    private struct CreateResponse: Decodable { let id: Int }

    @discardableResult
    func create(_ payload: ContactCreatePayload) async throws -> Int {
        let response: CreateResponse = try await client.request("/contacts/", method: .post, body: payload)
        return response.id
    }

    func update(_ contactId: Int, _ payload: ContactUpdatePayload) async throws {
        try await client.requestVoid("/contacts/\(contactId)", method: .patch, body: payload)
    }

    func bulkDelete(_ ids: [Int]) async throws {
        struct Body: Encodable { let ids: [Int] }
        try await client.requestVoid("/contacts/bulk", method: .delete, body: Body(ids: ids))
    }
}
