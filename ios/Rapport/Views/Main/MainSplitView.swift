import SwiftUI

/// Root navigation shell once logged in. NavigationSplitView adapts on its
/// own: three columns (sidebar/list/detail) on iPad in landscape or with
/// enough width, collapsing to a stack on iPhone and compact iPad
/// multitasking — this is the standard SwiftUI pattern for "optimized for
/// iPad, works everywhere" rather than a bespoke breakpoint system.
enum MainSection: String, CaseIterable, Identifiable {
    case applications, contacts, companies, calendar, analytics, settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .applications: "Applications"
        case .contacts: "Contacts"
        case .companies: "Companies"
        case .calendar: "Calendar"
        case .analytics: "Analytics"
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
        case .settings, nil:
            ContentUnavailableView(
                selectedSection?.title ?? "Rapport",
                systemImage: selectedSection?.systemImage ?? "square.dashed",
                description: Text("This section is coming soon.")
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
        default:
            Text("Select an item").foregroundStyle(.secondary)
        }
    }
}

#Preview {
    MainSplitView()
        .environment(SessionStore())
}
