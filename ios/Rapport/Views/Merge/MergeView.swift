import SwiftUI

/// Generic winner-take-all merge sheet — pick one winner and one or more
/// losers from the same candidate list, merge. Reused for applications,
/// contacts, and companies via `MergeViewModel`'s injected closures.
struct MergeView: View {
    @Environment(\.dismiss) private var dismiss
    @State var viewModel: MergeViewModel

    var body: some View {
        NavigationStack {
            List {
                Section("Winner (kept)") {
                    ForEach(viewModel.candidates) { candidate in
                        Button {
                            viewModel.winnerId = candidate.id
                            viewModel.selectedLoserIds.remove(candidate.id)
                        } label: {
                            HStack {
                                Text(candidate.label)
                                Spacer()
                                if viewModel.winnerId == candidate.id {
                                    Image(systemName: "checkmark").foregroundStyle(.blue)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }

                Section("Duplicates to merge in (removed after merge)") {
                    ForEach(viewModel.candidates.filter { $0.id != viewModel.winnerId }) { candidate in
                        Button {
                            if viewModel.selectedLoserIds.contains(candidate.id) {
                                viewModel.selectedLoserIds.remove(candidate.id)
                            } else {
                                viewModel.selectedLoserIds.insert(candidate.id)
                            }
                        } label: {
                            HStack {
                                Text(candidate.label)
                                Spacer()
                                if viewModel.selectedLoserIds.contains(candidate.id) {
                                    Image(systemName: "checkmark").foregroundStyle(.blue)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }

                if let errorMessage = viewModel.errorMessage {
                    Section { Text(errorMessage).foregroundStyle(.red) }
                }
                if let successMessage = viewModel.successMessage {
                    Section { Text(successMessage).foregroundStyle(.green) }
                }
            }
            .overlay {
                if viewModel.isLoading && viewModel.candidates.isEmpty { ProgressView() }
            }
            .navigationTitle("Merge duplicates")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Merge") { Task { await viewModel.merge() } }
                        .disabled(!viewModel.canMerge)
                }
            }
            .task { await viewModel.load() }
        }
    }
}
