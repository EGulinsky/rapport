import SwiftUI

enum SettingsPanel: String, CaseIterable, Identifiable {
    case account, syncControl, google, icloud, linkedin, files, backup, ai, maps, logo, agent

    var id: String { rawValue }

    var title: String {
        switch self {
        case .account: "Account"
        case .syncControl: "Sync sources"
        case .google: "Google"
        case .icloud: "iCloud"
        case .linkedin: "LinkedIn"
        case .files: "Local files"
        case .backup: "Backup"
        case .ai: "AI assessment"
        case .maps: "Maps"
        case .logo: "Company logos"
        case .agent: "Rapport Agent"
        }
    }

    var systemImage: String {
        switch self {
        case .account: "person.crop.circle"
        case .syncControl: "switch.2"
        case .google: "envelope"
        case .icloud: "icloud"
        case .linkedin: "link"
        case .files: "folder"
        case .backup: "externaldrive"
        case .ai: "sparkles"
        case .maps: "map"
        case .logo: "building.2.crop.circle"
        case .agent: "desktopcomputer"
        }
    }
}

struct SettingsHomeView: View {
    @Binding var selection: SettingsPanel?

    var body: some View {
        List(SettingsPanel.allCases, selection: $selection) { panel in
            Label(panel.title, systemImage: panel.systemImage).tag(panel)
        }
        .navigationTitle("Settings")
    }
}
