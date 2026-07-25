import SwiftUI

struct ReviewQueueView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: ReviewViewModel?

    var body: some View {
        Group {
            if let viewModel {
                List {
                    if viewModel.items.isEmpty && !viewModel.isLoading {
                        ContentUnavailableView("Nothing to review", systemImage: "checkmark.circle", description: Text("Sync-detected changes needing confirmation will show up here."))
                    }
                    ForEach(viewModel.items) { item in
                        ReviewRow(item: item, onApprove: {
                            Task { await viewModel.approve(item) }
                        }, onReject: {
                            Task { await viewModel.reject(item) }
                        })
                    }
                }
                .overlay {
                    if viewModel.isLoading && viewModel.items.isEmpty { ProgressView() }
                }
                .refreshable { await viewModel.load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Review")
        .task {
            if viewModel == nil {
                viewModel = ReviewViewModel(api: session.review)
                await viewModel?.load()
            }
        }
    }
}

private struct ReviewRow: View {
    let item: PendingMatchRead
    let onApprove: () -> Void
    let onReject: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(item.titel ?? item.eventType ?? item.source)
                    .font(.subheadline.bold())
                Spacer()
                Text("\(item.confidence)%")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let firma = item.suggestedAppFirma {
                Text("\(firma)\(item.suggestedAppRolle.map { " — \($0)" } ?? "")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let extract = item.extract, !extract.isEmpty {
                Text(extract)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
            Text(item.source)
                .font(.caption2)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Color(.tertiarySystemFill))
                .clipShape(Capsule())

            HStack {
                Button("Reject", role: .destructive, action: onReject)
                Spacer()
                Button("Approve", action: onApprove).buttonStyle(.borderedProminent)
            }
        }
        .padding(.vertical, 4)
    }
}
