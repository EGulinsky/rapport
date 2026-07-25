import SwiftUI

struct CalendarHomeView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: CalendarViewModel?

    var body: some View {
        Group {
            if let viewModel {
                List {
                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage).foregroundStyle(.red)
                    }
                    ForEach(viewModel.eventsByDay, id: \.day) { group in
                        Section(group.day) {
                            ForEach(group.events) { event in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(event.titel ?? event.typ).font(.subheadline.bold())
                                    Text("\(event.firma) — \(event.rolle)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                .overlay {
                    if viewModel.isLoading && viewModel.events.isEmpty {
                        ProgressView()
                    } else if viewModel.events.isEmpty {
                        ContentUnavailableView("No upcoming events", systemImage: "calendar")
                    }
                }
                .refreshable { await viewModel.load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Calendar")
        .task {
            if viewModel == nil {
                viewModel = CalendarViewModel(api: session.calendar)
                await viewModel?.load()
            }
        }
    }
}
