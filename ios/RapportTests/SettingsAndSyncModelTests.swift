import Testing
@testable import Rapport
import Foundation

struct SettingsAndSyncModelTests {
    // MARK: - SyncResult

    @Test func decodesSyncResultStubWithoutRequires2FA() throws {
        let json = """
        {"processed": 0, "created": 0, "skipped": 0, "errors": []}
        """
        let result = try APIClient.decoder.decode(SyncResult.self, from: Data(json.utf8))
        #expect(result.requiresTwoFa == false)
        #expect(result.updated == 0)
    }

    @Test func decodesSyncResultWithRequires2FATrue() throws {
        // Only /sync/icloud/notes/_legacy can ever set this true — verify the
        // explicit CodingKey actually maps "requires_2fa" correctly, since
        // Foundation's convertFromSnakeCase digit-handling isn't guaranteed.
        let json = """
        {"processed": 0, "created": 0, "skipped": 0, "errors": ["2FA required"], "requires_2fa": true}
        """
        let result = try APIClient.decoder.decode(SyncResult.self, from: Data(json.utf8))
        #expect(result.requiresTwoFa == true)
    }

    // MARK: - ManualAssignResult (three distinct response shapes)

    @Test func decodesManualAssignResultCreatedShape() throws {
        let json = """
        {"conflict": false, "event_id": 42}
        """
        let result = try APIClient.decoder.decode(ManualAssignResult.self, from: Data(json.utf8))
        #expect(result.conflict == false)
        #expect(result.eventId == 42)
        #expect(result.conflictAppId == nil)
    }

    @Test func decodesManualAssignResultConflictShapeWithoutEventId() throws {
        let json = """
        {"conflict": true, "conflict_app_id": 5, "conflict_app_firma": "Contoso", "conflict_event_id": 42}
        """
        let result = try APIClient.decoder.decode(ManualAssignResult.self, from: Data(json.utf8))
        #expect(result.conflict == true)
        #expect(result.eventId == nil)
        #expect(result.conflictAppFirma == "Contoso")
    }

    // MARK: - CompanySyncRunResult ("message" only present when started == false)

    @Test func decodesCompanySyncRunResultStartedWithoutMessage() throws {
        let json = """
        {"started": true, "count": 3}
        """
        let result = try APIClient.decoder.decode(CompanySyncRunResult.self, from: Data(json.utf8))
        #expect(result.started == true)
        #expect(result.message == nil)
    }

    @Test func decodesCompanySyncRunResultNotStartedWithMessage() throws {
        let json = """
        {"started": false, "count": 0, "message": "Already running"}
        """
        let result = try APIClient.decoder.decode(CompanySyncRunResult.self, from: Data(json.utf8))
        #expect(result.started == false)
        #expect(result.message == "Already running")
    }

    // MARK: - TargetedSyncResult (only "done" before completion)

    @Test func decodesTargetedSyncResultBeforeCompletion() throws {
        let json = """
        {"done": false}
        """
        let result = try APIClient.decoder.decode(TargetedSyncResult.self, from: Data(json.utf8))
        #expect(result.done == false)
        #expect(result.created == nil)
    }

    @Test func decodesTargetedSyncResultAfterCompletion() throws {
        let json = """
        {"done": true, "created": 2, "skipped": 1, "processed": 3, "errors": []}
        """
        let result = try APIClient.decoder.decode(TargetedSyncResult.self, from: Data(json.utf8))
        #expect(result.done == true)
        #expect(result.created == 2)
    }

    // MARK: - AgentHealth with per-module map

    @Test func decodesAgentHealthWithModulesMap() throws {
        let json = """
        {
          "reachable": true, "version": "1.2.3", "platform": "macOS",
          "modules": {
            "calls": {"ok": true, "phone_accessible": true, "whatsapp_accessible": false},
            "notes": {"ok": false, "error": "not authorized"}
          }
        }
        """
        let health = try APIClient.decoder.decode(AgentHealth.self, from: Data(json.utf8))
        #expect(health.modules["calls"]?.ok == true)
        #expect(health.modules["notes"]?.error == "not authorized")
    }

    // MARK: - BackupStatus with defensively-optional backup entries

    @Test func decodesBackupStatusWithBackupsArray() throws {
        let json = """
        {
          "enabled": true, "backup_folder": "/backups", "frequency_hours": 24,
          "keep_count": 7, "keep_daily": 14, "keep_weekly": 8, "last_backup": null,
          "backups": [{"name": "backup-1.db", "path": "/backups/backup-1.db", "modified": 1732000000.0, "size": 1024}]
        }
        """
        let status = try APIClient.decoder.decode(BackupStatus.self, from: Data(json.utf8))
        #expect(status.backups?.first?.name == "backup-1.db")
        #expect(status.lastBackup == nil)
    }

    // MARK: - SyncSettingsFlags round-trip (Codable both ways)

    @Test func syncSettingsFlagsRoundTripsThroughEncodeDecode() throws {
        let flags = SyncSettingsFlags(
            googleEnabled: true, gmailEnabled: true, gcalEnabled: false,
            icloudEnabled: true, icloudMailEnabled: true, icloudCalEnabled: false,
            icloudNotesEnabled: true, icloudRemindersEnabled: false, icloudContactsEnabled: true,
            icloudCallsEnabled: false, linkedinEnabled: true, filesEnabled: false,
            auditLogLevel: "verbose"
        )
        let data = try APIClient.encoder.encode(flags)
        let decoded = try APIClient.decoder.decode(SyncSettingsFlags.self, from: data)
        #expect(decoded.auditLogLevel == "verbose")
        #expect(decoded.icloudContactsEnabled == true)
        #expect(decoded.gcalEnabled == false)
    }

    // MARK: - ProfilePayload conditional uiLanguage encoding

    @Test func profilePayloadOmitsUiLanguageKeyWhenNil() throws {
        let payload = ProfilePayload(vorname: "Ada", nachname: nil, linkedinUrl: nil, homeLocation: nil, uiLanguage: nil)
        let data = try APIClient.encoder.encode(payload)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(object?.keys.contains("ui_language") == false)
        #expect(object?["vorname"] as? String == "Ada")
    }

    @Test func profilePayloadIncludesUiLanguageWhenSet() throws {
        let payload = ProfilePayload(uiLanguage: "de")
        let data = try APIClient.encoder.encode(payload)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(object?["ui_language"] as? String == "de")
    }

    @Test func profilePayloadEncodesNullForClearedFields() throws {
        let payload = ProfilePayload(vorname: nil, nachname: "Lovelace", linkedinUrl: nil, homeLocation: nil, uiLanguage: nil)
        let data = try APIClient.encoder.encode(payload)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(object?["vorname"] is NSNull)
        #expect(object?["nachname"] as? String == "Lovelace")
    }
}
