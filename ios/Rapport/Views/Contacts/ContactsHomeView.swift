import SwiftUI

/// Contacts has no GET-by-id endpoint (see the API catalog note in
/// contacts.py) — the detail view looks the selected contact up from this
/// same, shared view model rather than re-fetching, so the view model is
/// owned by MainSplitView and passed into both this view and the detail one.
struct ContactsHomeView: View {
    @Environment(SessionStore.self) private var session
    var viewModel: ContactsViewModel
    @Binding var selection: Int?
    @State private var showMerge = false

    var body: some View {
        List(selection: $selection) {
            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage).foregroundStyle(.red)
            }
            ForEach(viewModel.contacts) { contact in
                VStack(alignment: .leading, spacing: 2) {
                    Text(contact.displayName).font(.headline)
                    if let firma = contact.firma {
                        Text(firma).font(.subheadline).foregroundStyle(.secondary)
                    }
                    if let rolle = contact.rolle {
                        Text(rolle).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 2)
                .swipeActions {
                    Button("Delete", role: .destructive) {
                        Task { await viewModel.delete(contact) }
                    }
                }
            }
        }
        .overlay {
            if viewModel.isLoading && viewModel.contacts.isEmpty {
                ProgressView()
            } else if viewModel.contacts.isEmpty {
                ContentUnavailableView("No contacts yet", systemImage: "person.crop.circle")
            }
        }
        .refreshable { await viewModel.load() }
        .searchable(text: Bindable(viewModel).searchText)
        .onChange(of: viewModel.searchText) {
            Task { await viewModel.load() }
        }
        .navigationTitle("Contacts")
        .toolbar {
            ToolbarItem(placement: .secondaryAction) {
                Button {
                    showMerge = true
                } label: {
                    Label("Merge duplicates", systemImage: "arrow.triangle.merge")
                }
            }
        }
        .task {
            if viewModel.contacts.isEmpty {
                await viewModel.load()
            }
        }
        .sheet(isPresented: $showMerge) {
            MergeView(viewModel: MergeViewModel(
                fetchCandidates: {
                    try await session.contacts.list().map { MergeCandidate(id: $0.id, label: $0.displayName) }
                },
                performMerge: { winner, losers in
                    try await session.merge.mergeContacts(winnerId: winner, loserIds: losers)
                }
            ))
        }
    }
}
