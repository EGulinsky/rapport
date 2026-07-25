import SwiftUI

/// Content-column view for the Applications section: a List/Kanban toggle +
/// search, mirroring App.tsx's top-level view-mode switch. `selection`
/// drives the detail column in MainSplitView.
struct ApplicationsHomeView: View {
    @Environment(SessionStore.self) private var session
    @State private var viewModel: ApplicationsViewModel?
    @State private var displayMode: DisplayMode = .list
    @State private var showNewApplication = false
    @Binding var selection: Int?

    enum DisplayMode: String, CaseIterable, Identifiable {
        case list = "List", kanban = "Kanban"
        var id: String { rawValue }
    }

    var body: some View {
        Group {
            if let viewModel {
                content(viewModel)
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Applications")
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("View", selection: $displayMode) {
                    ForEach(DisplayMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .fixedSize()
            }
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showNewApplication = true
                } label: {
                    Label("New application", systemImage: "plus")
                }
            }
        }
        .searchable(text: Binding(
            get: { viewModel?.searchText ?? "" },
            set: { viewModel?.searchText = $0 }
        ))
        .task {
            if viewModel == nil {
                viewModel = ApplicationsViewModel(api: session.applications)
                await viewModel?.load()
            }
        }
        .onChange(of: viewModel?.searchText) {
            Task { await viewModel?.load() }
        }
        .sheet(isPresented: $showNewApplication) {
            if let viewModel {
                NewApplicationView(viewModel: viewModel)
            }
        }
    }

    @ViewBuilder
    private func content(_ viewModel: ApplicationsViewModel) -> some View {
        switch displayMode {
        case .list:
            ApplicationsListView(viewModel: viewModel, selection: $selection)
        case .kanban:
            KanbanBoardView(viewModel: viewModel, selection: $selection)
        }
    }
}
