import Foundation
import Observation

/// Backs the per-application "Sync" tab: the targeted (single-application)
/// sync trigger/reset, and the manual candidate-assignment flow
/// (sync_targeted.py's /candidates + /assign) that lets a user attach a
/// sync-detected item (email, calendar event, ...) to this application when
/// automatic matching didn't catch it.
@MainActor
@Observable
final class ManualSyncViewModel {
    private let api: TargetedSyncAPI
    let applicationId: Int

    private(set) var candidates: [ManualCandidate] = []
    var isLoading = false
    var isSyncing = false
    var errorMessage: String?
    var lastResultMessage: String?
    /// Set when an assign attempt reports a conflict — the view surfaces a
    /// confirmation to reassign (removeFromOther) or cancel.
    var pendingConflict: (candidate: ManualCandidate, result: ManualAssignResult)?

    private var pollTask: Task<Void, Never>?

    init(api: TargetedSyncAPI, applicationId: Int) {
        self.api = api
        self.applicationId = applicationId
    }

    func loadCandidates(query: String? = nil) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            candidates = try await api.candidates(appId: applicationId, query: query)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func triggerSync() async {
        errorMessage = nil
        isSyncing = true
        do {
            _ = try await api.trigger(appId: applicationId)
            startPollingResult()
        } catch let error as APIError {
            errorMessage = error.message
            isSyncing = false
        } catch {
            errorMessage = error.localizedDescription
            isSyncing = false
        }
    }

    private func startPollingResult() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                guard let result = try? await self.api.result(appId: self.applicationId) else { break }
                if result.done {
                    self.lastResultMessage = "Created \(result.created ?? 0) · Skipped \(result.skipped ?? 0)"
                    self.isSyncing = false
                    await self.loadCandidates()
                    break
                }
                try? await Task.sleep(nanoseconds: 1_500_000_000)
            }
        }
    }

    func resetSync() async {
        errorMessage = nil
        do {
            _ = try await api.reset(appId: applicationId)
            lastResultMessage = nil
            await loadCandidates()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func assign(_ candidate: ManualCandidate, removeFromOther: Bool = false) async -> ManualAssignResult? {
        errorMessage = nil
        do {
            let payload = ManualAssignPayload(
                matchId: candidate.id,
                externalId: candidate.externalId,
                source: candidate.source,
                eventType: candidate.eventType,
                datum: candidate.datum,
                titel: candidate.titel,
                removeFromOther: removeFromOther
            )
            let result = try await api.assign(appId: applicationId, payload: payload)
            if result.conflict && !removeFromOther {
                pendingConflict = (candidate, result)
            } else {
                candidates.removeAll { $0.id == candidate.id }
                pendingConflict = nil
            }
            return result
        } catch let error as APIError {
            errorMessage = error.message
            return nil
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func confirmPendingConflict() async {
        guard let pending = pendingConflict else { return }
        pendingConflict = nil
        await assign(pending.candidate, removeFromOther: true)
    }

    func cancelPendingConflict() {
        pendingConflict = nil
    }
}
