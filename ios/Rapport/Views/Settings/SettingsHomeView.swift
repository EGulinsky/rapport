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

    /// Which labeled section this panel belongs to — grouping the 11 panels
    /// this way (instead of one flat 11-row list) mirrors the web app's
    /// SettingsModal, which also separates account/sync/integrations/data.
    var group: SettingsGroup {
        switch self {
        case .account: .account
        case .syncControl, .google, .icloud, .linkedin, .files: .syncSources
        case .ai, .maps, .logo, .agent: .integrations
        case .backup: .data
        }
    }
}

enum SettingsGroup: String, CaseIterable, Identifiable {
    case account, syncSources, integrations, data

    var id: String { rawValue }

    var title: String {
        switch self {
        case .account: "Account"
        case .syncSources: "Sync sources"
        case .integrations: "Integrations"
        case .data: "Data"
        }
    }
}

struct SettingsHomeView: View {
    @Binding var selection: SettingsPanel?

    var body: some View {
        List(selection: $selection) {
            ForEach(SettingsGroup.allCases) { group in
                let panels = SettingsPanel.allCases.filter { $0.group == group }
                // .account is a single-item group whose only row's label
                // ("Account") is identical to the group's own title — a
                // header here would just repeat it. Every other group has
                // multiple distinctly-named rows, so a header adds real
                // information there.
                if group == .account {
                    Section {
                        ForEach(panels) { panel in
                            Label(panel.title, systemImage: panel.systemImage).tag(panel)
                        }
                    }
                } else {
                    Section(group.title) {
                        ForEach(panels) { panel in
                            Label(panel.title, systemImage: panel.systemImage).tag(panel)
                        }
                    }
                }
            }
        }
        .navigationTitle("Settings")
    }
}
