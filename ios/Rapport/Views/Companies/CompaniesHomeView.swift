import SwiftUI

struct CompaniesHomeView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: CompaniesViewModel?
    @State private var showNewCompany = false
    @Binding var selection: Int?

    var body: some View {
        Group {
            if let viewModel {
                List(selection: $selection) {
                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage).foregroundStyle(.red)
                    }
                    ForEach(viewModel.companies) { company in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(company.nameDisplay ?? company.nameNorm).font(.headline)
                            HStack(spacing: 8) {
                                if let industry = company.industry {
                                    Text(industry).font(.caption).foregroundStyle(.secondary)
                                }
                                if let count = company.appCount, count > 0 {
                                    Text("\(count) application\(count == 1 ? "" : "s")")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        .padding(.vertical, 2)
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
        }
        .task {
            if viewModel == nil {
                viewModel = CompaniesViewModel(api: session.companies)
                await viewModel?.load()
            }
        }
        .sheet(isPresented: $showNewCompany) {
            if let viewModel {
                NewCompanyView(viewModel: viewModel)
            }
        }
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
