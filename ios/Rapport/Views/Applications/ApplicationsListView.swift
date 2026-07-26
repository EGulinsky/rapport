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
        HStack(alignment: .top, spacing: 10) {
            CompanyAvatar(name: application.firma, color: application.mainStatus.color)
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
        }
        .padding(.vertical, 2)
        .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 2)
                .fill(application.mainStatus.color)
                .frame(width: 3)
        }
        .padding(.leading, 8)
    }
}

struct StatusChip: View {
    let status: MainStatus

    var body: some View {
        Text(status.label)
            .font(.caption2.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(status.color.opacity(0.15))
            .foregroundStyle(status.color)
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
