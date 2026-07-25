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
    }

    @ViewBuilder
    private var sectionContent: some View {
        switch selectedSection {
        case .applications:
            ApplicationsHomeView(selection: $selectedApplicationId)
        case .contacts, .companies, .calendar, .analytics, .settings, nil:
            ContentUnavailableView(
                selectedSection?.title ?? "Rapport",
                systemImage: selectedSection?.systemImage ?? "square.dashed",
                description: Text("This section is coming soon.")
            )
        }
    }

    @ViewBuilder
    private var detailContent: some View {
        if selectedSection == .applications, let id = selectedApplicationId {
            ApplicationDetailView(applicationId: id) { _ in }
        } else {
            Text("Select an item")
                .foregroundStyle(.secondary)
        }
    }
}

#Preview {
    MainSplitView()
        .environment(SessionStore())
}
