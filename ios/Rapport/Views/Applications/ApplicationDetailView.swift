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
        case overview = "Overview", timeline = "Timeline", contacts = "Contacts", salary = "Salary", sync = "Sync"
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
                    case .sync: SyncTab(applicationId: applicationId)
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

/// Per-application manual sync + candidate assignment — the native
/// counterpart to the web app's "targeted sync" flow (sync_targeted.py):
/// trigger a sync scoped to just this application, or manually attach a
/// sync-detected item (email/calendar event/...) that automatic matching
/// missed. A separate "Sync via LinkedIn" trigger targets this one job
/// posting rather than a full-account LinkedIn sync (see Settings).
private struct SyncTab: View {
    let applicationId: Int
    @Environment(SessionStore.self) private var session
    @State private var viewModel: ManualSyncViewModel?
    @State private var linkedInStatusMessage: String?
    @State private var isLinkedInSyncing = false

    var body: some View {
        Group {
            if let viewModel {
                Form {
                    Section("Targeted sync") {
                        Button("Sync now") { Task { await viewModel.triggerSync() } }
                            .disabled(viewModel.isSyncing)
                        Button("Reset", role: .destructive) { Task { await viewModel.resetSync() } }
                        if viewModel.isSyncing {
                            ProgressView()
                        }
                        if let message = viewModel.lastResultMessage {
                            Text(message).font(.caption).foregroundStyle(.secondary)
                        }
                    }

                    Section("LinkedIn") {
                        Button("Sync via LinkedIn") {
                            Task {
                                isLinkedInSyncing = true
                                linkedInStatusMessage = nil
                                do {
                                    let state = try await session.linkedinSync.run(targetAppId: applicationId)
                                    linkedInStatusMessage = state.step
                                } catch let error as APIError {
                                    linkedInStatusMessage = error.message
                                } catch {
                                    linkedInStatusMessage = error.localizedDescription
                                }
                                isLinkedInSyncing = false
                            }
                        }
                        .disabled(isLinkedInSyncing)
                        if isLinkedInSyncing {
                            ProgressView()
                        }
                        if let linkedInStatusMessage {
                            Text(linkedInStatusMessage).font(.caption).foregroundStyle(.secondary)
                        }
                    }

                    Section("Candidates") {
                        if viewModel.candidates.isEmpty {
                            Text("No unmatched items found").font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(viewModel.candidates) { candidate in
                            CandidateRow(candidate: candidate) {
                                Task { await viewModel.assign(candidate) }
                            }
                        }
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Section { Text(errorMessage).foregroundStyle(.red) }
                    }
                }
                .refreshable { await viewModel.loadCandidates() }
                .alert(
                    "Already assigned elsewhere",
                    isPresented: Binding(
                        get: { viewModel.pendingConflict != nil },
                        set: { if !$0 { viewModel.cancelPendingConflict() } }
                    ),
                    presenting: viewModel.pendingConflict
                ) { pending in
                    Button("Reassign here", role: .destructive) {
                        Task { await viewModel.confirmPendingConflict() }
                    }
                    Button("Cancel", role: .cancel) { viewModel.cancelPendingConflict() }
                } message: { pending in
                    Text("This item is currently linked to \(pending.result.conflictAppFirma ?? "another application"). Reassign it to this one instead?")
                }
            } else {
                ProgressView()
            }
        }
        .task {
            if viewModel == nil {
                viewModel = ManualSyncViewModel(api: session.targetedSync, applicationId: applicationId)
                await viewModel?.loadCandidates()
            }
        }
    }
}

private struct CandidateRow: View {
    let candidate: ManualCandidate
    let onAssign: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(candidate.titel ?? candidate.eventType ?? candidate.source).font(.subheadline.bold())
                Spacer()
                Text("\(candidate.confidence)%").font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: 8) {
                Text(candidate.source).font(.caption2).foregroundStyle(.secondary)
                if let datum = candidate.datum {
                    Text(datum).font(.caption2).foregroundStyle(.secondary)
                }
            }
            if let extract = candidate.extract, !extract.isEmpty {
                Text(extract).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
            }
            Button("Assign", action: onAssign)
                .font(.caption)
        }
        .padding(.vertical, 2)
    }
}
