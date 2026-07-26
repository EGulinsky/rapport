import SwiftUI

struct CompaniesHomeView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: CompaniesViewModel?
    @State private var syncViewModel: CompanySyncViewModel?
    @State private var showNewCompany = false
    @State private var showMerge = false
    @Binding var selection: Int?

    var body: some View {
        Group {
            if let viewModel {
                List(selection: $selection) {
                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage).foregroundStyle(.red)
                    }
                    if let syncStatus = syncViewModel?.status, syncStatus.running || syncStatus.pending > 0 {
                        CompanySyncBanner(status: syncStatus) {
                            Task { await syncViewModel?.cancel() }
                        }
                    }
                    ForEach(viewModel.companies) { company in
                        CompanyRow(company: company)
                    }
                }
                .overlay {
                    if viewModel.isLoading && viewModel.companies.isEmpty {
                        ProgressView()
                    } else if viewModel.companies.isEmpty {
                        ContentUnavailableView("No companies yet", systemImage: "building.2")
                    }
                }
                .refreshable { await viewModel.load() }
                .searchable(text: Bindable(viewModel).searchText)
                .onChange(of: viewModel.searchText) {
                    Task { await viewModel.load() }
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Companies")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showNewCompany = true } label: { Label("New company", systemImage: "plus") }
            }
            ToolbarItem(placement: .secondaryAction) {
                Button { showMerge = true } label: { Label("Merge duplicates", systemImage: "arrow.triangle.merge") }
            }
            ToolbarItem(placement: .secondaryAction) {
                Button {
                    Task {
                        await syncViewModel?.run()
                        await viewModel?.load()
                    }
                } label: {
                    Label("Sync from LinkedIn", systemImage: "arrow.triangle.2.circlepath")
                }
                .disabled(syncViewModel?.status?.running == true)
            }
        }
        .task {
            if viewModel == nil {
                viewModel = CompaniesViewModel(api: session.companies)
                await viewModel?.load()
            }
            if syncViewModel == nil {
                syncViewModel = CompanySyncViewModel(api: session.companySync)
                await syncViewModel?.load()
            }
        }
        .sheet(isPresented: $showNewCompany) {
            if let viewModel {
                NewCompanyView(viewModel: viewModel)
            }
        }
        .sheet(isPresented: $showMerge) {
            MergeView(viewModel: MergeViewModel(
                fetchCandidates: {
                    try await session.companies.list().map { MergeCandidate(id: $0.id, label: $0.nameDisplay ?? $0.nameNorm) }
                },
                performMerge: { winner, losers in
                    try await session.merge.mergeCompanies(winnerId: winner, loserIds: losers)
                }
            ))
        }
    }
}

private struct CompanyRow: View {
    let company: CompanyProfile

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(company.nameDisplay ?? company.nameNorm).font(.headline)
            HStack(spacing: 8) {
                if let industry = company.industry {
                    Text(industry).font(.caption).foregroundStyle(.secondary)
                }
                if let count = company.appCount, count > 0 {
                    let suffix = count == 1 ? "" : "s"
                    Text("\(count) application\(suffix)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

/// Live status banner for the company data-enrichment sync
/// (sync_company.py — pulls industry/size/logo from LinkedIn for companies
/// whose profile is still pending). `CompanySyncViewModel.run()` polls
/// `GET /sync/company/status` on a 2s interval while running, so this
/// updates without the user needing to pull-to-refresh.
private struct CompanySyncBanner: View {
    let status: CompanySyncStatus
    let onCancel: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                if status.running {
                    Text(status.currentCompany.map { "Syncing \($0)…" } ?? "Syncing…")
                        .font(.subheadline)
                } else {
                    Text("\(status.pending) companies pending sync").font(.subheadline)
                }
                Text("Done \(status.done) · Failed \(status.failed) · Needs review \(status.needsReview)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if status.running {
                Button("Cancel", action: onCancel).font(.caption)
            }
        }
        .padding(.vertical, 4)
    }
}

private struct NewCompanyView: View {
    var viewModel: CompaniesViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                TextField("Company name", text: $name)
                if let errorMessage {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }
            .navigationTitle("New company")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            do {
                                _ = try await viewModel.create(name: name)
                                dismiss()
                            } catch let error as APIError {
                                errorMessage = error.message
                            } catch {
                                errorMessage = error.localizedDescription
                            }
                        }
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
    }
}
