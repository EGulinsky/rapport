import Foundation

/// Mirrors backend/app/schemas.py's ApplicationBrief — the minimal shape
/// embedded in Contact.applications and CompanyProfile.applications.
struct ApplicationBrief: Codable, Identifiable, Equatable {
    let id: Int
    var firma: String
    var rolle: String
    var companyNameDisplay: String?
    /// Only present on CompanyProfile.applications (not Contact.applications) —
    /// optional either way since both share this one struct.
    var mainStatus: String?
    var datumBewerbung: String?
}

/// A company hierarchy child reference (CompanyProfile.subsidiaries).
struct CompanySubsidiary: Codable, Identifiable, Equatable {
    let id: Int
    var nameDisplay: String?
    var nameNorm: String
}

/// Mirrors frontend/src/types.ts's CompanyProfile interface (the backend
/// exposes this shape via companies.py — no single matching Pydantic schema
/// name since it's assembled ad hoc; see the API surface catalog for the
/// exact companies.py endpoints once available).
struct CompanyProfile: Codable, Identifiable, Equatable {
    let id: Int
    var nameDisplay: String?
    var nameNorm: String
    var industry: String?
    var companyType: String?
    var employeeRange: String?
    var employeeCount: Int?
    var foundedYear: Int?
    var hqCity: String?
    var hqCountry: String?
    var website: String?
    var linkedinCompanyUrl: String?
    var description: String?
    var syncSource: String?
    var syncStatus: String
    var syncError: String?
    var lastSyncedAt: String?
    var appCount: Int?
    var contactCount: Int?
    var hasLogo: Bool?
    var logoData: String?
    var parentCompanyId: Int?
    var parentName: String?
    var subsidiaries: [CompanySubsidiary]?
    var applications: [ApplicationBrief]?
}
