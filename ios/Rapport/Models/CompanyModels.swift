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

/// Mirrors companies.py's CompanyContactPhoneRef (embedded in CompanyContactRef,
/// not the same shape as the main ContactPhone struct's source model but
/// identical fields, so a distinct type isn't needed for decoding —
/// kept separate anyway to match the backend's own distinct response model
/// and avoid coupling companies.py's contract to contacts.py's.
struct CompanyContactPhoneRef: Codable, Identifiable, Equatable {
    let id: Int
    var number: String
    var type: String
}

/// Mirrors companies.py's CompanyContactRef — the contact shape embedded in
/// CompanyProfileDetail.contacts (narrower than the full Contact model).
struct CompanyContactRef: Codable, Identifiable, Equatable {
    let id: Int
    var name: String
    var vorname: String?
    var email: String?
    var phones: [CompanyContactPhoneRef]
    var linkedinUrl: String?
    var firma: String?
    var rolle: String?
    var typ: String?

    var displayName: String {
        if let vorname, !vorname.trimmingCharacters(in: .whitespaces).isEmpty {
            return "\(vorname) \(name)"
        }
        return name
    }
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
    /// Only present on CompanyProfileDetail (GET /api/companies/{id}), absent
    /// from CompanyProfileListItem (GET /api/companies) — same
    /// list-vs-detail asymmetry as Application.ghosting, see ApplicationModels.swift.
    var contacts: [CompanyContactRef]?
}

/// Mirrors companies.py's CompanyCreateRequest / CompanyUpdateRequest.
struct CompanyCreatePayload: Encodable {
    var name: String
}

struct CompanyUpdatePayload: Encodable {
    var nameDisplay: String?
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
    var parentCompanyId: Int?
}
