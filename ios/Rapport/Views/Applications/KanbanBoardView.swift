import SwiftUI
import UniformTypeIdentifiers

/// Drag payload for moving a card between columns — just the id, since the
/// drop handler looks the full Application back up in the view model rather
/// than round-tripping the whole object through the pasteboard.
private struct KanbanCardTransfer: Codable, Transferable {
    let applicationId: Int

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .rapportKanbanCard)
    }
}

private extension UTType {
    static let rapportKanbanCard = UTType(exportedAs: "com.rapport.ios.kanban-card")
}

/// Horizontally-scrolling board, one column per MainStatus.pipeline entry —
/// mirrors KanbanBoard.tsx. Dropping a card on a column PATCHes main_status
/// (and clears sub_status when leaving hr/fb).
struct KanbanBoardView: View {
    var viewModel: ApplicationsViewModel
    @Binding var selection: Int?

    var body: some View {
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 12) {
                ForEach(MainStatus.pipeline) { status in
                    KanbanColumn(
                        status: status,
                        applications: viewModel.applications(in: status),
                        selection: $selection,
                        onDrop: { appId in
                            if let app = viewModel.applications.first(where: { $0.id == appId }) {
                                Task { await viewModel.updateStatus(app, to: status) }
                            }
                        }
                    )
                }
            }
            .padding()
        }
        .overlay {
            if viewModel.isLoading && viewModel.applications.isEmpty {
                ProgressView()
            }
        }
        .refreshable { await viewModel.load() }
    }
}

private struct KanbanColumn: View {
    let status: MainStatus
    let applications: [Application]
    @Binding var selection: Int?
    let onDrop: (Int) -> Void

    @State private var isTargeted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(status.label).font(.subheadline.bold())
                Spacer()
                Text("\(applications.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(applications) { app in
                        KanbanCard(application: app)
                            .onTapGesture { selection = app.id }
                            .draggable(KanbanCardTransfer(applicationId: app.id))
                    }
                }
            }
        }
        .frame(width: 260)
        .padding(8)
        .background(isTargeted ? Color.accentColor.opacity(0.1) : Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .dropDestination(for: KanbanCardTransfer.self) { items, _ in
            guard let first = items.first else { return false }
            onDrop(first.applicationId)
            return true
        } isTargeted: { isTargeted = $0 }
    }
}

private struct KanbanCard: View {
    let application: Application

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(application.firma).font(.subheadline.bold())
            Text(application.rolle).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            if let step = application.naechsterSchritt, !step.isEmpty {
                Text(step).font(.caption2).foregroundStyle(.blue).lineLimit(2)
            }
            HStack(spacing: 6) {
                if application.salaryMismatch {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange).font(.caption2)
                }
                if application.ghosting == true {
                    Image(systemName: "wind").foregroundStyle(.gray).font(.caption2)
                }
                if let color = application.aiColor {
                    Circle()
                        .fill(aiColor(color))
                        .frame(width: 8, height: 8)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .shadow(color: .black.opacity(0.06), radius: 2, y: 1)
    }

    private func aiColor(_ raw: String) -> Color {
        switch raw {
        case "green": .green
        case "yellow": .yellow
        case "red": .red
        default: .clear
        }
    }
}
