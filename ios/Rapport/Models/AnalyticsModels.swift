import Foundation

/// Mirrors analytics.py's GET /api/analytics/summary — an untyped dict on
/// the backend (no Pydantic schema), transcribed here field-for-field per
/// the API catalog. Note several field names contain "ä" (gespräch,
/// gespräch_rate) — convertFromSnakeCase capitalizes only the first letter
/// of each component, so `avgDaysToGespräch` etc. decode correctly without
/// custom CodingKeys.
struct AnalyticsSummary: Decodable {
    struct KPIs: Decodable {
        var total: Int
        var active: Int
        var rejected: Int
        var signed: Int
        var ghostingCount: Int
        var ghostingRate: Double
        var hhCount: Int
        var directCount: Int
        var hhPct: Double
        var conversionGespräch: Double
        var conversionOffer: Double
        var avgDaysToGespräch: Double?
        var avgDaysAppliedToRejected: Double?
    }

    struct FunnelStage: Decodable, Identifiable {
        var status: String
        var label: String
        var count: Int
        var pct: Double
        var id: String { status }
    }

    struct MonthCount: Decodable, Identifiable {
        var month: String
        var label: String
        var count: Int
        var id: String { month }
    }

    struct SourceCount: Decodable, Identifiable {
        var source: String
        var count: Int
        var id: String { source }
    }

    struct HHDirectBucket: Decodable {
        var total: Int
        var gespräch: Int
        var offer: Int
    }

    struct HHVsDirect: Decodable {
        var hh: HHDirectBucket
        var direct: HHDirectBucket
    }

    struct RejectionByStatus: Decodable, Identifiable {
        var status: String
        var label: String
        var count: Int
        var id: String { status }
    }

    struct CompanySync: Decodable {
        var total: Int
        var pending: Int
        var done: Int
        var failed: Int
    }

    struct StageConversion: Decodable, Identifiable {
        var fromStatus: String
        var fromLabel: String
        var toStatus: String
        var toLabel: String
        var rate: Double
        var dropOff: Int
        var id: String { fromStatus + toStatus }
    }

    struct CategoryBreakdown: Decodable, Identifiable {
        var label: String
        var total: Int
        var gespräch: Int
        var offer: Int
        var gesprächRate: Double
        var offerRate: Double
        var id: String { label }
    }

    var kpis: KPIs
    var funnel: [FunnelStage]
    var byMonth: [MonthCount]
    var bySource: [SourceCount]
    var hhVsDirect: HHVsDirect
    var rejectionByStatus: [RejectionByStatus]
    var companySync: CompanySync
    var stageConversions: [StageConversion]
    var bottleneck: StageConversion?
    var byCompanyType: [CategoryBreakdown]
    var byEmployeeRange: [CategoryBreakdown]
    var byRoleCategory: [CategoryBreakdown]
}
