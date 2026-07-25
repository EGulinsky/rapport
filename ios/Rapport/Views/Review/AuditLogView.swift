import SwiftUI

struct AuditLogView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: AuditLogViewModel?

    var body: some View {
        Group {
            if let viewModel {
                List {
                    Section {
                        Picker("Entity type", selection: Binding(
                            get: { viewModel.entityTypeFilter ?? "all" },
                            set: { newValue in
                                viewModel.entityTypeFilter = newValue == "all" ? nil : newValue
                                Task { await viewModel.load() }
                            }
                        )) {
                            Text("All").tag("all")
                            Text("Applications").tag("application")
                            Text("Contacts").tag("contact")
                            Text("Companies").tag("company")
                            Text("Events").tag("event")
                        }
                    }
                    Section("\(viewModel.total) entries") {
                        ForEach(viewModel.entries) { entry in
                            AuditLogRow(entry: entry)
                        }
                    }
                }
                .overlay {
                    if viewModel.isLoading && viewModel.entries.isEmpty { ProgressView() }
                }
                .refreshable { await viewModel.load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Audit Log")
        .task {
            if viewModel == nil {
                viewModel = AuditLogViewModel(api: session.auditLog)
                await viewModel?.load()
            }
        }
    }
}

private struct AuditLogRow: View {
    let entry: AuditLogEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(entry.action).font(.caption.bold())
                Text(entry.source).font(.caption).foregroundStyle(.secondary)
                Spacer()
                if let timestamp = entry.timestamp {
                    Text(DateParsing.displayString(timestamp)).font(.caption2).foregroundStyle(.secondary)
                }
            }
            if let target = entry.appFirma ?? entry.contactName ?? entry.companyName ?? entry.eventTitel {
                Text(target).font(.subheadline)
            }
            if let field = entry.field {
                Text("\(field): \(entry.oldValue ?? "—") → \(entry.newValue ?? "—")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if let reason = entry.reason, !reason.isEmpty {
                Text(reason).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}
