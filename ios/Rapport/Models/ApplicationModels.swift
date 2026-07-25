import Foundation

/// Mirrors frontend/src/types.ts's unified `Application` interface, which
/// itself covers the union of backend/app/schemas.py's ApplicationListItem
/// (GET /api/applications/) and ApplicationRead (GET /api/applications/{id})
/// — every field either response might omit is optional here, exactly as
/// the frontend does, rather than splitting into two structs that would
/// mostly duplicate each other.
struct Application: Codable, Identifiable, Equatable {
    let id: Int
    var firma: String
    var rolle: String
    var mainStatus: MainStatus
    var subStatus: String?
    var preRejectionStatus: String?
    var isHeadhunter: Bool
    var zielfirmaBeiHh: String?
    var quelle: String?
    var wurdeBesetztVon: String?
    var ort: String?
    var datumBewerbung: String?
    var letztesUpdate: String?
    /// Computed server-side per request (applications.py's
    /// _compute_naechster_schritt()) — not stored, so it's absent from
    /// ApplicationUpdatePayload entirely.
    var naechsterSchritt: String?
    var abgesagt: Bool
    /// Only present on ApplicationListItem (GET /api/applications/) — absent
    /// from ApplicationRead (GET /api/applications/{id}), per schemas.py.
    /// Optional here rather than defaulting to false so a detail-only fetch
    /// can't be mistaken for "confirmed not ghosting".
    var ghosting: Bool?
    var kommentar: String?
    var stellenanzeigeUrl: String?
    var gespraech1: String?
    var gespraech2: String?
    var gespraech3: String?
    var gespraech4: String?
    var gespraech5: String?
    var contacts: [Contact]?
    var events: [Event]?
    var companyProfileId: Int?
    var targetCompanyProfileId: Int?
    var companyWebsite: String?
    var targetCompanyWebsite: String?
    var companyNameDisplay: String?
    var targetCompanyNameDisplay: String?
    var aiColor: String?
    var aiNextStep: String?
    var aiReasoning: String?
    var aiAssessedAt: String?
    var salaryCurrency: String?
    var salaryExpectationMin: Int?
    var salaryExpectationMax: Int?
    var salaryBudgetMin: Int?
    var salaryBudgetMax: Int?
    var salaryExpectationMinFixed: Int?
    var salaryExpectationMinBonus: Int?
    var salaryExpectationMaxFixed: Int?
    var salaryExpectationMaxBonus: Int?
    var salaryBudgetMinFixed: Int?
    var salaryBudgetMinBonus: Int?
    var salaryBudgetMaxFixed: Int?
    var salaryBudgetMaxBonus: Int?
    var salaryExpectationCompanyCar: Bool?
    var salaryBudgetCompanyCar: Bool?
    var salaryMismatch: Bool
    var driveDistanceKm: Double?
    var driveDurationMin: Double?
    var createdAt: String?
    var updatedAt: String?

    /// "green"/"yellow"/"red" traffic light from the AI assessment, or nil
    /// if never assessed.
    enum AIColor: String {
        case green, yellow, red
    }
}

/// Mirrors backend/app/schemas.py's ApplicationCreate.
struct ApplicationCreatePayload: Encodable {
    var firma: String
    var rolle: String
    var mainStatus: String = "applied"
    var subStatus: String?
    var isHeadhunter: Bool = false
    var zielfirmaBeiHh: String?
    var quelle: String?
    var ort: String?
    var datumBewerbung: String?
    var kommentar: String?
    var stellenanzeigeUrl: String?
    var createdFromLinkedin: Bool = false
}

/// Mirrors backend/app/schemas.py's ApplicationUpdate — every field optional
/// (a partial PATCH only touches what's set).
struct ApplicationUpdatePayload: Encodable {
    var firma: String?
    var companyProfileId: Int?
    var targetCompanyProfileId: Int?
    var rolle: String?
    var mainStatus: String?
    var subStatus: String?
    var isHeadhunter: Bool?
    var zielfirmaBeiHh: String?
    var quelle: String?
    var wurdeBesetztVon: String?
    var ort: String?
    var datumBewerbung: String?
    var letztesUpdate: String?
    var kommentar: String?
    var stellenanzeigeUrl: String?
    var gespraech1: String?
    var gespraech2: String?
    var gespraech3: String?
    var gespraech4: String?
    var gespraech5: String?
    var salaryCurrency: String?
    var salaryExpectationMin: Int?
    var salaryExpectationMax: Int?
    var salaryBudgetMin: Int?
    var salaryBudgetMax: Int?
}
