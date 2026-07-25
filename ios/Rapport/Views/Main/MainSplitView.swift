import SwiftUI

/// Root navigation shell once logged in. NavigationSplitView adapts on its
/// own: three columns (sidebar/list/detail) on iPad in landscape or with
/// enough width, collapsing to a stack on iPhone and compact iPad
/// multitasking — this is the standard SwiftUI pattern for "optimized for
/// iPad, works everywhere" rather than a bespoke breakpoint system.
enum MainSection: String, CaseIterable, Identifiable {
    case applications, contacts, companies, calendar, analytics, review, auditLog, settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .applications: "Applications"
        case .contacts: "Contacts"
        case .companies: "Companies"
        case .calendar: "Calendar"
        case .analytics: "Analytics"
        case .review: "Review"
        case .auditLog: "Audit Log"
        case .settings: "Settings"
        }
    }

    var systemImage: String {
        switch self {
        case .applications: "briefcase"
        case .contacts: "person.crop.circle"
        case .companies: "building.2"
        case .calendar: "calendar"
        case .analytics: "chart.bar"
        case .review: "checklist"
        case .auditLog: "list.bullet.clipboard"
        case .settings: "gearshape"
        }
    }
}

struct MainSplitView: View {
    @Environment(SessionStore.self) private var session
    @State private var selectedSection: MainSection? = .applications
    @State private var columnVisibility: NavigationSplitViewVisibility = .automatic
    @State private var selectedApplicationId: Int?
    @State private var selectedContactId: Int?
    @State private var selectedCompanyId: Int?
    @State private var contactsViewModel: ContactsViewModel?
    @State private var selectedSettingsPanel: SettingsPanel?

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            List(MainSection.allCases, selection: $selectedSection) { section in
                Label(section.title, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationTitle("Rapport")
            .safeAreaInset(edge: .bottom) {
                if let user = session.currentUser {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(user.displayName).font(.subheadline.bold())
                            Text(user.email).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("Sign out", role: .destructive) {
                            session.logout()
                        }
                        .font(.caption)
                    }
                    .padding()
                    .background(.bar)
                }
            }
        } content: {
            sectionContent
        } detail: {
            detailContent
        }
        .task {
            if contactsViewModel == nil {
                contactsViewModel = ContactsViewModel(api: session.contacts)
            }
        }
    }

    @ViewBuilder
    private var sectionContent: some View {
        switch selectedSection {
        case .applications:
            ApplicationsHomeView(selection: $selectedApplicationId)
        case .contacts:
            if let contactsViewModel {
                ContactsHomeView(viewModel: contactsViewModel, selection: $selectedContactId)
            } else {
                ProgressView()
            }
        case .companies:
            CompaniesHomeView(selection: $selectedCompanyId)
        case .calendar:
            CalendarHomeView()
        case .analytics:
            AnalyticsHomeView()
        case .review:
            ReviewQueueView()
        case .auditLog:
            AuditLogView()
        case .settings:
            SettingsHomeView(selection: $selectedSettingsPanel)
        case nil:
            ContentUnavailableView(
                "Rapport",
                systemImage: "square.dashed",
                description: Text("Select a section.")
            )
        }
    }

    @ViewBuilder
    private var detailContent: some View {
        switch selectedSection {
        case .applications:
            if let id = selectedApplicationId {
                ApplicationDetailView(applicationId: id) { _ in }
            } else {
                Text("Select an item").foregroundStyle(.secondary)
            }
        case .contacts:
            if let id = selectedContactId, let contact = contactsViewModel?.contacts.first(where: { $0.id == id }) {
                ContactDetailView(contact: contact)
            } else {
                Text("Select a contact").foregroundStyle(.secondary)
            }
        case .companies:
            if let id = selectedCompanyId {
                CompanyDetailView(companyId: id)
            } else {
                Text("Select a company").foregroundStyle(.secondary)
            }
        case .settings:
            settingsDetailContent
        default:
            Text("Select an item").foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var settingsDetailContent: some View {
        switch selectedSettingsPanel {
        case .account:
            AccountSettingsView()
        case .syncControl:
            SyncControlSettingsView()
        case .google:
            GoogleSyncSettingsView()
        case .icloud:
            ICloudSyncSettingsView()
        case .linkedin:
            LinkedInSettingsView()
        case .files:
            FilesSettingsView()
        case .backup:
            BackupSettingsView()
        case .ai:
            AiSettingsView()
        case .maps:
            ApiKeySettingsView(
                title: "Maps",
                helpText: "Google Maps API key, used to compute distance from your home location to each application's site.",
                hasKey: { $0.hasKey },
                load: { try await session.settings.mapsSettings() },
                save: { try await session.settings.updateMapsSettings(MapsSettingsPayload(apiKey: $0)) },
                delete: { try await session.settings.deleteMapsKey() }
            )
        case .logo:
            ApiKeySettingsView(
                title: "Company logos",
                helpText: "Logo.dev API key, used to fetch company logos shown on Kanban cards and company profiles.",
                supportsDelete: false,
                hasKey: { $0.apiKey != nil },
                load: { try await session.settings.logoSettings() },
                save: { try await session.settings.updateLogoSettings(LogoSettingsPayload(apiKey: $0)) }
            )
        case .agent:
            AgentSettingsView()
        case nil:
            Text("Select a settings category").foregroundStyle(.secondary)
        }
    }
}

#Preview {
    MainSplitView()
        .environment(SessionStore())
}
