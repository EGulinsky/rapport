import SwiftUI

/// Detail column content for a selected application — mirrors
/// ApplicationModal.tsx's tabbed layout (a subset of its tabs for now:
/// Overview, Timeline, Contacts, Salary; Attachments/AI reasoning detail
/// follow in a later pass).
struct ApplicationDetailView: View {
    let applicationId: Int
    let onUpdate: (Application) -> Void

    @Environment(SessionStore.self) private var session
    @State private var viewModel: ApplicationDetailViewModel?
    @State private var tab: Tab = .overview

    enum Tab: String, CaseIterable, Identifiable {
        case overview = "Overview", timeline = "Timeline", contacts = "Contacts", salary = "Salary"
        var id: String { rawValue }
    }

    var body: some View {
        Group {
            if let viewModel, let application = viewModel.application {
                VStack(spacing: 0) {
                    Picker("Tab", selection: $tab) {
                        ForEach(Tab.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .padding()

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage).foregroundStyle(.red).padding(.horizontal)
                    }

                    switch tab {
                    case .overview: OverviewTab(application: application, viewModel: viewModel)
                    case .timeline: TimelineTab(application: application, viewModel: viewModel)
                    case .contacts: ContactsTab(application: application, viewModel: viewModel)
                    case .salary: SalaryTab(application: application, viewModel: viewModel)
                    }
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle(viewModel?.application?.firma ?? "")
        .task(id: applicationId) {
            let vm = ApplicationDetailViewModel(api: session.applications, applicationId: applicationId)
            vm.onUpdate = onUpdate
            viewModel = vm
            await vm.load()
        }
    }
}

private struct OverviewTab: View {
    let application: Application
    var viewModel: ApplicationDetailViewModel
    @State private var mainStatus: MainStatus = .applied

    var body: some View {
        Form {
            Section("Status") {
                Picker("Status", selection: $mainStatus) {
                    ForEach(MainStatus.allCases) { Text($0.label).tag($0) }
                }
                .onAppear { mainStatus = application.mainStatus }
                .onChange(of: mainStatus) { _, newValue in
                    guard newValue != application.mainStatus else { return }
                    Task { await viewModel.update(ApplicationUpdatePayload(mainStatus: newValue.rawValue)) }
                }
            }
            Section("Role") {
                LabeledContent("Company", value: application.firma)
                LabeledContent("Role", value: application.rolle)
                if let ort = application.ort { LabeledContent("Location", value: ort) }
                if let quelle = application.quelle { LabeledContent("Source", value: quelle) }
            }
            if let ai = application.aiNextStep, !ai.isEmpty {
                Section("AI next step") {
                    Text(ai)
                    if let reasoning = application.aiReasoning, !reasoning.isEmpty {
                        Text(reasoning).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Section {
                Button("Request AI assessment") {
                    Task { await viewModel.requestAIAssessment() }
                }
            }
            if let kommentar = application.kommentar, !kommentar.isEmpty {
                Section("Comment") {
                    Text(kommentar)
                }
            }
        }
    }
}

private struct TimelineTab: View {
    let application: Application
    var viewModel: ApplicationDetailViewModel
    @State private var showAddEvent = false

    var body: some View {
        List {
            ForEach((application.events ?? []).sorted { ($0.datum ?? "") > ($1.datum ?? "") }) { event in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(event.titel ?? event.typ).font(.subheadline.bold())
                        Spacer()
                        if let datum = event.datum { Text(datum).font(.caption).foregroundStyle(.secondary) }
                    }
                    if let notiz = event.notiz, !notiz.isEmpty {
                        Text(notiz).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                    }
                }
                .swipeActions {
                    Button("Delete", role: .destructive) {
                        Task { await viewModel.deleteEvent(event) }
                    }
                }
            }
        }
        .overlay {
            if (application.events ?? []).isEmpty {
                ContentUnavailableView("No timeline entries yet", systemImage: "clock")
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showAddEvent = true } label: { Label("Add", systemImage: "plus") }
            }
        }
        .sheet(isPresented: $showAddEvent) {
            AddEventSheet(viewModel: viewModel)
        }
    }
}

private struct AddEventSheet: View {
    var viewModel: ApplicationDetailViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var typ = "notiz"
    @State private var titel = ""
    @State private var notiz = ""
    @State private var datum = Date()

    var body: some View {
        NavigationStack {
            Form {
                Picker("Type", selection: $typ) {
                    Text("Note").tag("notiz")
                    Text("Interview").tag("gespräch")
                    Text("Application").tag("bewerbung")
                }
                DatePicker("Date", selection: $datum, displayedComponents: .date)
                TextField("Title", text: $titel)
                TextField("Note", text: $notiz, axis: .vertical)
            }
            .navigationTitle("New entry")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            await viewModel.addEvent(typ: typ, titel: titel.isEmpty ? nil : titel, notiz: notiz.isEmpty ? nil : notiz, datum: datum)
                            dismiss()
                        }
                    }
                }
            }
        }
    }
}

private struct ContactsTab: View {
    let application: Application
    var viewModel: ApplicationDetailViewModel
    @State private var showAddContact = false

    var body: some View {
        List {
            ForEach(application.contacts ?? []) { contact in
                VStack(alignment: .leading, spacing: 2) {
                    Text(contact.displayName).font(.subheadline.bold())
                    if let rolle = contact.rolle { Text(rolle).font(.caption).foregroundStyle(.secondary) }
                    if let email = contact.email { Text(email).font(.caption).foregroundStyle(.secondary) }
                }
                .swipeActions {
                    Button("Remove", role: .destructive) {
                        Task { await viewModel.removeContact(contact) }
                    }
                }
            }
        }
        .overlay {
            if (application.contacts ?? []).isEmpty {
                ContentUnavailableView("No contacts linked yet", systemImage: "person.crop.circle")
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showAddContact = true } label: { Label("Add", systemImage: "plus") }
            }
        }
        .sheet(isPresented: $showAddContact) {
            AddContactSheet(viewModel: viewModel)
        }
    }
}

private struct AddContactSheet: View {
    var viewModel: ApplicationDetailViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var email = ""
    @State private var rolle = ""

    var body: some View {
        NavigationStack {
            Form {
                TextField("Name", text: $name)
                TextField("Email", text: $email).keyboardType(.emailAddress).textInputAutocapitalization(.never)
                TextField("Role", text: $rolle)
            }
            .navigationTitle("New contact")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            await viewModel.addContact(name: name, email: email, rolle: rolle.isEmpty ? nil : rolle)
                            dismiss()
                        }
                    }
                    .disabled(name.isEmpty || email.isEmpty)
                }
            }
        }
    }
}

private struct SalaryTab: View {
    let application: Application
    var viewModel: ApplicationDetailViewModel

    var body: some View {
        Form {
            if application.salaryMismatch {
                Section {
                    Label("Budget doesn't cover the expectation", systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                }
            }
            Section("Expectation") {
                salaryRow(min: application.salaryExpectationMin, max: application.salaryExpectationMax, currency: application.salaryCurrency)
            }
            Section("Company budget") {
                salaryRow(min: application.salaryBudgetMin, max: application.salaryBudgetMax, currency: application.salaryCurrency)
            }
        }
    }

    @ViewBuilder
    private func salaryRow(min: Int?, max: Int?, currency: String?) -> some View {
        if min == nil && max == nil {
            Text("Not set").foregroundStyle(.secondary)
        } else {
            let currencyCode = currency ?? "EUR"
            if let min, let max, min != max {
                Text("\(min.formatted())–\(max.formatted()) \(currencyCode)")
            } else {
                Text("\((min ?? max ?? 0).formatted()) \(currencyCode)")
            }
        }
    }
}
