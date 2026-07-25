import Foundation

/// The backend serializes dates in two shapes depending on the field
/// (Pydantic `date` -> "2026-07-24", `datetime` -> "2026-07-24T15:30:00" or
/// with a timezone/fractional seconds). Rather than fight a single global
/// JSONDecoder date strategy across mixed shapes in the same payload, model
/// fields stay plain `String?` (matching frontend/src/types.ts) and callers
/// parse on demand for display via these helpers.
enum DateParsing {
    private static let dateOnlyFormatter: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    // ISO8601DateFormatter isn't marked Sendable, but these are configured
    // once and only ever read (never mutated) afterward from this app's
    // single-threaded (MainActor) view-layer call sites.
    nonisolated(unsafe) private static let isoWithFractional = ISO8601DateFormatter().with {
        $0.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    }
    nonisolated(unsafe) private static let isoPlain = ISO8601DateFormatter().with {
        $0.formatOptions = [.withInternetDateTime]
    }
    private static let naiveDateTimeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()
    private static let naiveDateTimeWithFractionFormatter: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    /// Parses a date-only string ("2026-07-24").
    static func date(_ string: String?) -> Date? {
        guard let string else { return nil }
        return dateOnlyFormatter.date(from: string)
    }

    /// Parses a datetime string in any of the shapes the backend produces:
    /// with timezone + fractional seconds, with timezone only, or naive
    /// (no timezone at all, treated as UTC — matches how sync-derived
    /// timestamps are stored, see backend/app/routers/sync_common.py's
    /// _to_naive_utc()).
    static func dateTime(_ string: String?) -> Date? {
        guard let string else { return nil }
        if let d = isoWithFractional.date(from: string) { return d }
        if let d = isoPlain.date(from: string) { return d }
        if let d = naiveDateTimeWithFractionFormatter.date(from: string) { return d }
        if let d = naiveDateTimeFormatter.date(from: string) { return d }
        return nil
    }
}

private extension ISO8601DateFormatter {
    func with(_ configure: (ISO8601DateFormatter) -> Void) -> ISO8601DateFormatter {
        configure(self)
        return self
    }
}
