import SwiftUI

/// Contacts has no GET-by-id endpoint (see the API catalog note in
/// contacts.py) — the detail view looks the selected contact up from this
/// same, shared view model rather than re-fetching, so the view model is
/// owned by MainSplitView and passed into both this view and the detail one.
struct ContactsHomeView: View {
    var viewModel: ContactsViewModel
    @Binding var selection: Int?

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
        .task {
            if viewModel.contacts.isEmpty {
                await viewModel.load()
            }
        }
    }
}
