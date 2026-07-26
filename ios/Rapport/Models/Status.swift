import Foundation
import SwiftUI

/// Mirrors backend/app/models.py's MainStatus enum + MAIN_STATUS_LABELS and
/// frontend/src/i18n/locales/en/status.json's English labels (kept in sync
/// manually until iOS i18n is wired up — see the i18n task).
enum MainStatus: String, Codable, CaseIterable, Identifiable {
    case prospecting, applied, hr, fb, waiting, negotiating, signed, rejected

    var id: String { rawValue }

    var label: String {
        switch self {
        case .prospecting: "Prospecting"
        case .applied: "Applied"
        case .hr: "Interview (HR)"
        case .fb: "Interview (Team)"
        case .waiting: "Awaiting decision"
        case .negotiating: "Offer negotiation"
        case .signed: "Signed"
        case .rejected: "Rejected"
        }
    }

    /// The Kanban board's columns — rejected is shown separately (a toggle
    /// reveals it), matching KanbanBoard.tsx's MAIN_PIPELINE.
    static let pipeline: [MainStatus] = [.prospecting, .applied, .hr, .fb, .waiting, .negotiating, .signed]

    /// Single source of truth for this status's accent color, shared by the
    /// list row, the Kanban card's left border, and the status pill — the
    /// prior design used the same color logic copy-pasted in each place,
    /// which could drift, and the same status looked different on the board
    /// vs. the list.
    var color: Color {
        switch self {
        case .prospecting: .gray
        case .applied: .blue
        case .hr: .orange
        case .fb: .purple
        case .waiting: .pink
        case .negotiating: .green
        case .signed: .mint
        case .rejected: .red
        }
    }
}

/// Mirrors backend/app/models.py's SUB_STATUS_LABELS — only meaningful when
/// mainStatus is .hr or .fb.
enum SubStatus: String, Codable, CaseIterable, Identifiable {
    case scheduled1 = "1_scheduled", done1 = "1_done"
    case scheduled2 = "2_scheduled", done2 = "2_done"
    case scheduled3 = "3_scheduled", done3 = "3_done"
    case scheduled4 = "4_scheduled", done4 = "4_done"
    case scheduled5 = "5_scheduled", done5 = "5_done"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .scheduled1: "1st interview scheduled"
        case .done1: "1st interview completed"
        case .scheduled2: "2nd interview scheduled"
        case .done2: "2nd interview completed"
        case .scheduled3: "3rd interview scheduled"
        case .done3: "3rd interview completed"
        case .scheduled4: "4th interview scheduled"
        case .done4: "4th interview completed"
        case .scheduled5: "5th interview scheduled"
        case .done5: "5th interview completed"
        }
    }

    static let sequence: [SubStatus] = [.scheduled1, .done1, .scheduled2, .done2, .scheduled3, .done3, .scheduled4, .done4, .scheduled5, .done5]
}
