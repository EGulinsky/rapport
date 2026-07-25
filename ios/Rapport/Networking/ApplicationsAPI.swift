import Foundation

/// Wraps APIClient calls for backend/app/routers/applications.py's endpoints
/// (prefix "/api/applications"). Mirrors frontend/src/api/client.ts's
/// `api.applications` namespace.
struct ApplicationsAPI {
    let client: APIClient

    func list(mainStatus: String? = nil, search: String? = nil, companyProfileId: Int? = nil, showRejected: Bool = false) async throws -> [Application] {
        try await client.request(
            "/applications/",
            query: [
                "main_status": mainStatus,
                "search": search,
                "company_profile_id": companyProfileId.map(String.init),
                "show_rejected": String(showRejected),
            ]
        )
    }

    func get(_ id: Int) async throws -> Application {
        try await client.request("/applications/\(id)")
    }

    func create(_ payload: ApplicationCreatePayload) async throws -> Application {
        try await client.request("/applications/", method: .post, body: payload)
    }

    func update(_ id: Int, _ payload: ApplicationUpdatePayload) async throws -> Application {
        try await client.request("/applications/\(id)", method: .patch, body: payload)
    }

    func delete(_ id: Int) async throws {
        try await client.requestVoid("/applications/\(id)", method: .delete)
    }

    func stats() async throws -> Stats {
        try await client.request("/applications/stats")
    }

    // MARK: - Events

    func addEvent(_ appId: Int, _ payload: EventCreatePayload) async throws -> Event {
        try await client.request("/applications/\(appId)/events", method: .post, body: payload)
    }

    func updateEvent(_ appId: Int, _ eventId: Int, _ payload: EventUpdatePayload) async throws -> Event {
        try await client.request("/applications/\(appId)/events/\(eventId)", method: .patch, body: payload)
    }

    func deleteEvent(_ appId: Int, _ eventId: Int) async throws {
        try await client.requestVoid("/applications/\(appId)/events/\(eventId)", method: .delete)
    }

    // MARK: - Contacts

    func addContact(_ appId: Int, _ payload: ContactCreatePayload) async throws -> Contact {
        try await client.request("/applications/\(appId)/contacts", method: .post, body: payload)
    }

    func linkContact(_ appId: Int, _ contactId: Int) async throws -> Contact {
        try await client.request("/applications/\(appId)/contacts/\(contactId)", method: .put)
    }

    func deleteContact(_ appId: Int, _ contactId: Int) async throws {
        try await client.requestVoid("/applications/\(appId)/contacts/\(contactId)", method: .delete)
    }

    func aiAssess(_ appId: Int) async throws {
        try await client.requestVoid("/applications/\(appId)/ai-assess", method: .post)
    }
}

/// Mirrors backend/app/schemas.py's StatsResponse.
struct Stats: Decodable {
    var total: Int
    var active: Int
    var rejected: Int
    var byStatus: [String: Int]
}
