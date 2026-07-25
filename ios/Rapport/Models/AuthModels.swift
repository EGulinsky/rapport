import Foundation

// Mirrors backend/app/routers/auth.py's Pydantic payload/response models.
// Property names are camelCase; APIClient's JSONDecoder/JSONEncoder use
// convertFromSnakeCase/convertToSnakeCase so no explicit CodingKeys are needed.

struct RegisterPayload: Encodable {
    let email: String
    let password: String
    let uiLanguage: String
}

struct VerifyEmailPayload: Encodable {
    let email: String
    let code: String
}

struct ResendCodePayload: Encodable {
    let email: String
}

struct LoginPayload: Encodable {
    let email: String
    let password: String
}

struct ForgotPasswordPayload: Encodable {
    let email: String
}

struct ResetPasswordPayload: Encodable {
    let email: String
    let code: String
    let newPassword: String
}

struct ChangePasswordPayload: Encodable {
    let oldPassword: String
    let newPassword: String
}

/// `PATCH /api/auth/profile` request. `uiLanguage` is only sent when
/// actually changed — omitting a key here (vs. sending `null`) matters:
/// the backend only applies `ui_language` if the key is present at all,
/// to avoid an unrelated profile save silently resetting the account's
/// language back to a default.
struct ProfilePayload: Encodable {
    var vorname: String?
    var nachname: String?
    var linkedinUrl: String?
    var homeLocation: String?
    var uiLanguage: String?

    enum CodingKeys: String, CodingKey {
        case vorname, nachname, linkedinUrl, homeLocation, uiLanguage
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(vorname, forKey: .vorname)
        try container.encode(nachname, forKey: .nachname)
        try container.encode(linkedinUrl, forKey: .linkedinUrl)
        try container.encode(homeLocation, forKey: .homeLocation)
        if let uiLanguage {
            try container.encode(uiLanguage, forKey: .uiLanguage)
        }
    }
}

struct AuthTokenResponse: Decodable {
    let accessToken: String
    let tokenType: String
}

struct UserResponse: Decodable, Identifiable, Equatable {
    let id: Int
    let email: String
    let emailVerified: Bool
    let vorname: String?
    let nachname: String?
    let linkedinUrl: String?
    let cvFilename: String?
    let cvSizeBytes: Int?
    let linkedinProfileSyncedAt: String?
    let uiLanguage: String
    let homeLocation: String?
    let homeLat: Double?
    let homeLng: Double?

    /// Matches ContactsView-style display-name fallback used throughout the
    /// web app: prefer "Vorname Nachname", fall back to the email's local part.
    var displayName: String {
        let name = [vorname, nachname].compactMap { $0 }.joined(separator: " ")
        if !name.trimmingCharacters(in: .whitespaces).isEmpty { return name }
        return String(email.split(separator: "@").first ?? Substring(email))
    }
}

struct MessageResponse: Decodable {
    let message: String
}
