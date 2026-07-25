import Testing
@testable import Rapport
import Foundation

struct ReviewAuditMergeTests {
    @Test func decodesPendingMatchWithOnlyRequiredFields() throws {
        let json = """
        {"id": 1, "source": "gmail", "confidence": 80, "status_only": false}
        """
        let match = try APIClient.decoder.decode(PendingMatchRead.self, from: Data(json.utf8))
        #expect(match.eventType == nil)
        #expect(match.suggestedAppId == nil)
        #expect(match.statusOnly == false)
    }

    @Test func decodesPendingMatchDuplicateContactWithJsonEncodedRawContent() throws {
        // duplicate_contact carries structured data inside `raw_content` as a
        // JSON string, not a nested object — kept as a raw String on
        // purpose since its shape depends entirely on event_type.
        let json = """
        {
          "id": 2, "source": "cleanup", "confidence": 100, "status_only": false,
          "event_type": "duplicate_contact",
          "raw_content": "{\\"keeper_contact_id\\": 5, \\"dup_contact_id\\": 9}"
        }
        """
        let match = try APIClient.decoder.decode(PendingMatchRead.self, from: Data(json.utf8))
        #expect(match.rawContent?.contains("keeper_contact_id") == true)
    }

    @Test func approveMatchResultEventIdIsNullableForCompanyCandidates() throws {
        let json = """
        {"status": "approved", "event_id": null}
        """
        let result = try APIClient.decoder.decode(ApproveMatchResult.self, from: Data(json.utf8))
        #expect(result.eventId == nil)
        #expect(result.status == "approved")
    }

    @Test func auditLogResponseDecodesEntitiesWithFreeTextFields() throws {
        let json = """
        {
          "total": 2,
          "items": [
            {"id": 1, "action": "update", "source": "gmail", "entity_type": "application",
             "app_id": 5, "app_firma": "Contoso", "field": "main_status", "old_value": "applied", "new_value": "hr"},
            {"id": 2, "action": "some_future_action_value", "source": "a_new_sync_source_not_yet_known"}
          ]
        }
        """
        let response = try APIClient.decoder.decode(AuditLogResponse.self, from: Data(json.utf8))
        #expect(response.total == 2)
        #expect(response.items[0].appFirma == "Contoso")
        // Free-text action/source fields must decode even with values the
        // Swift client has never seen — this is why they're String, not an enum.
        #expect(response.items[1].action == "some_future_action_value")
    }

    @Test func mergeRequestPayloadAlwaysSendsEmptyFieldOverrides() throws {
        let payload = MergeRequestPayload(winnerId: 1, loserIds: [2, 3])
        let data = try APIClient.encoder.encode(payload)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(object?["winner_id"] as? Int == 1)
        #expect(object?["loser_ids"] as? [Int] == [2, 3])
        #expect((object?["field_overrides"] as? [String: Int])?.isEmpty == true)
    }

    @MainActor
    @Test func mergeViewModelCanMergeRequiresWinnerAndNonOverlappingLosers() async {
        let viewModel = MergeViewModel(
            fetchCandidates: { [MergeCandidate(id: 1, label: "A"), MergeCandidate(id: 2, label: "B")] },
            performMerge: { _, _ in MergeResult(success: true, winnerId: 1) }
        )
        await viewModel.load()
        #expect(viewModel.canMerge == false)

        viewModel.winnerId = 1
        #expect(viewModel.canMerge == false) // no losers selected yet

        viewModel.selectedLoserIds = [2]
        #expect(viewModel.canMerge == true)

        viewModel.selectedLoserIds = [1] // same as winner — invalid
        #expect(viewModel.canMerge == false)
    }
}
