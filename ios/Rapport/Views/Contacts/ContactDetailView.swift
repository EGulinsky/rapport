import SwiftUI

struct ContactDetailView: View {
    let contact: Contact
    @Environment(SessionStore.self) private var session
    @State private var viewModel: ContactDetailViewModel?
    @State private var tab: Tab = .info

    enum Tab: String, CaseIterable, Identifiable {
        case info = "Info", calls = "Calls", mails = "Mail", messages = "LinkedIn", calendar = "Calendar"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("Tab", selection: $tab) {
                ForEach(Tab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .padding()

            switch tab {
            case .info: InfoTab(contact: contact)
            case .calls: EventList(items: viewModel?.events?.calls ?? [], emptyLabel: "No calls yet")
            case .mails: EventList(items: viewModel?.events?.mails ?? [], emptyLabel: "No mail yet")
            case .messages: EventList(items: viewModel?.events?.messages ?? [], emptyLabel: "No LinkedIn messages yet")
            case .calendar: EventList(items: viewModel?.events?.calendar ?? [], emptyLabel: "No calendar events yet")
            }
        }
        .navigationTitle(contact.displayName)
        .task(id: contact.id) {
            let vm = ContactDetailViewModel(api: session.contacts, contactId: contact.id)
            viewModel = vm
            await vm.load()
        }
    }
}

private struct InfoTab: View {
    let contact: Contact

    var body: some View {
        Form {
            Section {
                if let email = contact.email { LabeledContent("Email", value: email) }
                if let firma = contact.firma { LabeledContent("Company", value: firma) }
                if let rolle = contact.rolle { LabeledContent("Role", value: rolle) }
                if let typ = contact.typ { LabeledContent("Type", value: typ) }
            }
            if !contact.phones.isEmpty {
                Section("Phone numbers") {
                    ForEach(contact.phones) { phone in
                        LabeledContent(phone.type, value: phone.number)
                    }
                }
            }
            if let notizen = contact.notizen, !notizen.isEmpty {
                Section("Notes") {
                    Text(notizen)
                }
            }
            if let applications = contact.applications, !applications.isEmpty {
                Section("Applications") {
                    ForEach(applications) { app in
                        VStack(alignment: .leading) {
                            Text(app.firma).font(.subheadline.bold())
                            Text(app.rolle).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }
}

private struct EventList: View {
    let items: [ContactEventItem]
    let emptyLabel: String

    var body: some View {
        List(items) { item in
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(item.titel ?? item.typ).font(.subheadline.bold())
                    Spacer()
                    if let datum = item.datum { Text(datum).font(.caption).foregroundStyle(.secondary) }
                }
                if let companyName = item.companyName {
                    Text(companyName).font(.caption).foregroundStyle(.secondary)
                }
                if let notiz = item.notiz, !notiz.isEmpty {
                    Text(notiz).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                }
            }
        }
        .overlay {
            if items.isEmpty {
                ContentUnavailableView(emptyLabel, systemImage: "tray")
            }
        }
    }
}
