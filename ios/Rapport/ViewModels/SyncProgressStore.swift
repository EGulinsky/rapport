import Foundation
import Observation

/// Polls the shared progress/batch-results endpoints (see `SyncProgressAPI`)
/// on a 1.5s interval while at least one caller has asked it to run, so any
/// Settings panel showing a sync-in-progress source updates live without
/// each panel running its own timer. Mirrors the web app's SyncButton
/// polling loop.
@MainActor
@Observable
final class SyncProgressStore {
    private let api: SyncProgressAPI
    private(set) var progress: [String: ProgressEntry] = [:]
    private(set) var batchResults: [String: BatchResult] = [:]
    private var pollTask: Task<Void, Never>?
    private var activeSources = Set<String>()

    init(api: SyncProgressAPI) {
        self.api = api
    }

    /// Call when a view starts caring about a given source (e.g. right
    /// after triggering a sync). Starts the poll loop if not already
    /// running; stops automatically once no source is active anymore.
    func watch(_ source: String) {
        activeSources.insert(source)
        startIfNeeded()
    }

    func stopWatching(_ source: String) {
        activeSources.remove(source)
    }

    func isDone(_ source: String) -> Bool {
        progress[source]?.done ?? batchResults[source]?.done ?? false
    }

    private func startIfNeeded() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                await self.refresh()
                if await self.activeSources.isEmpty { break }
                try? await Task.sleep(nanoseconds: 1_500_000_000)
            }
            await MainActor.run { self?.pollTask = nil }
        }
    }

    private func refresh() async {
        do {
            progress = try await api.progress()
            batchResults = try await api.batchResults()
        } catch {
            // Transient network hiccups shouldn't kill the poll loop; the
            // next tick will simply try again.
        }
    }
}
