import SwiftUI

struct ApplicationsListView: View {
    var viewModel: ApplicationsViewModel
    @Binding var selection: Int?

    var body: some View {
        List(selection: $selection) {
            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage).foregroundStyle(.red)
            }
            ForEach(viewModel.applications) { app in
                ApplicationRow(application: app)
                    .swipeActions {
                        Button("Delete", role: .destructive) {
                            Task { await viewModel.delete(app) }
                        }
                    }
            }
        }
        .overlay {
            if viewModel.isLoading && viewModel.applications.isEmpty {
                ProgressView()
            } else if viewModel.applications.isEmpty {
                ContentUnavailableView("No applications yet", systemImage: "briefcase")
            }
        }
        .refreshable { await viewModel.load() }
    }
}

struct ApplicationRow: View {
    let application: Application

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(application.firma).font(.headline)
                Spacer()
                if application.salaryMismatch {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                        .accessibilityLabel("Salary mismatch")
                }
                if application.ghosting == true {
                    Image(systemName: "wind")
                        .foregroundStyle(.gray)
                        .accessibilityLabel("Possibly ghosted")
                }
            }
            Text(application.rolle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            HStack(spacing: 6) {
                StatusChip(status: application.mainStatus)
                if let step = application.naechsterSchritt, !step.isEmpty {
                    Text(step)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

struct StatusChip: View {
    let status: MainStatus

    var color: Color {
        switch status {
        case .prospecting: .gray
        case .applied: .blue
        case .hr: .yellow
        case .fb: .purple
        case .waiting: .pink
        case .negotiating: .green
        case .signed: .mint
        case .rejected: .red
        }
    }

    var body: some View {
        Text(status.label)
            .font(.caption2.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

#Preview {
    NavigationStack {
        ApplicationsListView(
            viewModel: ApplicationsViewModel(api: ApplicationsAPI(client: APIClient())),
            selection: .constant(nil)
        )
    }
}
