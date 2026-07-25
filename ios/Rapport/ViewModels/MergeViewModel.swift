import Foundation
import Observation

struct MergeCandidate: Identifiable, Hashable {
    var id: Int
    var label: String
}

/// Generic winner-take-all merge flow, reused for applications/contacts/
/// companies via closures the caller supplies (fetch the candidate list,
/// perform the actual merge call) rather than three near-identical view
/// models.
@MainActor
@Observable
final class MergeViewModel {
    private let fetchCandidates: () async throws -> [MergeCandidate]
    private let performMerge: (Int, [Int]) async throws -> MergeResult

    private(set) var candidates: [MergeCandidate] = []
    var winnerId: Int?
    var selectedLoserIds: Set<Int> = []
    var isLoading = false
    var errorMessage: String?
    var successMessage: String?

    init(
        fetchCandidates: @escaping () async throws -> [MergeCandidate],
        performMerge: @escaping (Int, [Int]) async throws -> MergeResult
    ) {
        self.fetchCandidates = fetchCandidates
        self.performMerge = performMerge
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            candidates = try await fetchCandidates()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    var canMerge: Bool {
        guard let winnerId else { return false }
        return !selectedLoserIds.isEmpty && !selectedLoserIds.contains(winnerId)
    }

    func merge() async {
        guard let winnerId, canMerge else { return }
        errorMessage = nil
        do {
            let result = try await performMerge(winnerId, Array(selectedLoserIds))
            successMessage = "Merged \(selectedLoserIds.count) duplicate(s) into the selected winner."
            candidates.removeAll { selectedLoserIds.contains($0.id) }
            selectedLoserIds.removeAll()
            _ = result
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
