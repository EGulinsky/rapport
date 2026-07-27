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
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @State private var selectedSection: MainSection? = .applications
    @State private var columnVisibility: NavigationSplitViewVisibility = .automatic
    @State private var selectedApplicationId: Int?
    @State private var selectedContactId: Int?
    @State private var selectedCompanyId: Int?
    @State private var contactsViewModel: ContactsViewModel?
    @State private var selectedSettingsPanel: SettingsPanel?

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            sidebarContent
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

    /// Regular width (iPad, side-by-side multitasking excluded) gets the
    /// persistent icon-only rail — a fixed 64pt strip is wasted space as a
    /// full text list once there's a content column right next to it, since
    /// the icon alone is enough to identify a section you already know.
    /// Compact width (iPhone, narrow iPad multitasking) keeps the original
    /// full list: collapsed presentation shows this column at full screen
    /// width, where a bare icon rail would leave most of the screen empty.
    @ViewBuilder
    private var sidebarContent: some View {
        if horizontalSizeClass == .regular {
            sidebarRail
                .navigationSplitViewColumnWidth(min: 64, ideal: 64, max: 64)
        } else {
            sidebarList
        }
    }

    private var sidebarList: some View {
        List(MainSection.allCases, selection: $selectedSection) { section in
            Label(section.title, systemImage: section.systemImage)
                .tag(section)
                // Distinguishes the sidebar row from same-named text
                // elsewhere (e.g. the content column's own navigationTitle,
                // which can coincidentally overlap the Kanban/List toggle's
                // screen coordinates in the collapsed iPad layout) —
                // UI tests target this instead of matching on visible text.
                // `.accessibilityElement(children: .combine)` is required
                // here: without it, the identifier attaches to the SF
                // Symbol icon's own leaf accessibility element (which
                // XCUITest then reports as "not hittable", since the row's
                // real tap target is the merged label, not the bare icon).
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("sidebar.\(section.rawValue)")
        }
        .navigationTitle("Rapport")
        .safeAreaInset(edge: .bottom) {
            userFooter
        }
    }

    private var sidebarRail: some View {
        VStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 9)
                .fill(Color.accentColor)
                .frame(width: 30, height: 30)
                .padding(.top, 16)
                .padding(.bottom, 10)
                .accessibilityHidden(true)

            ForEach(MainSection.allCases) { section in
                Button {
                    selectedSection = section
                } label: {
                    Image(systemName: section.systemImage)
                        .font(.system(size: 18))
                        .frame(width: 44, height: 40)
                        .background(selectedSection == section ? Color.accentColor.opacity(0.15) : Color.clear)
                        .foregroundStyle(selectedSection == section ? Color.accentColor : Color.secondary)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(section.title)
                .accessibilityIdentifier("sidebar.\(section.rawValue)")
            }

            Spacer()

            if session.currentUser != nil {
                Button(role: .destructive) {
                    session.logout()
                } label: {
                    Image(systemName: "rectangle.portrait.and.arrow.right")
                        .font(.system(size: 16))
                        .frame(width: 44, height: 40)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.red)
                .accessibilityLabel("Sign out")
                .padding(.bottom, 12)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .toolbar(.hidden, for: .navigationBar)
    }

    private var userFooter: some View {
        Group {
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
