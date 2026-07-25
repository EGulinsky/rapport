import SwiftUI

struct CompanyDetailView: View {
    let companyId: Int
    @Environment(SessionStore.self) private var session
    @State private var viewModel: CompanyDetailViewModel?

    var body: some View {
        Group {
            if let viewModel, let company = viewModel.company {
                Form {
                    Section {
                        LabeledContent("Name", value: company.nameDisplay ?? company.nameNorm)
                        if let industry = company.industry { LabeledContent("Industry", value: industry) }
                        if let hqCity = company.hqCity { LabeledContent("HQ", value: [hqCity, company.hqCountry].compactMap { $0 }.joined(separator: ", ")) }
                        if let website = company.website { LabeledContent("Website", value: website) }
                        if let range = company.employeeRange { LabeledContent("Employees", value: range) }
                    }
                    if let applications = company.applications, !applications.isEmpty {
                        Section("Applications") {
                            ForEach(applications) { app in
                                VStack(alignment: .leading) {
                                    Text(app.rolle).font(.subheadline.bold())
                                    if let status = app.mainStatus, let main = MainStatus(rawValue: status) {
                                        StatusChip(status: main)
                                    }
                                }
                            }
                        }
                    }
                    if let contacts = company.contacts, !contacts.isEmpty {
                        Section("Contacts") {
                            ForEach(contacts) { contact in
                                VStack(alignment: .leading) {
                                    Text(contact.displayName).font(.subheadline.bold())
                                    if let rolle = contact.rolle { Text(rolle).font(.caption).foregroundStyle(.secondary) }
                                }
                            }
                        }
                    }
                    if let subsidiaries = company.subsidiaries, !subsidiaries.isEmpty {
                        Section("Subsidiaries") {
                            ForEach(subsidiaries) { sub in
                                Text(sub.nameDisplay ?? sub.nameNorm)
                            }
                        }
                    }
                }
                .navigationTitle(company.nameDisplay ?? company.nameNorm)
            } else {
                ProgressView()
            }
        }
        .task(id: companyId) {
            let vm = CompanyDetailViewModel(api: session.companies, companyId: companyId)
            viewModel = vm
            await vm.load()
        }
    }
}
