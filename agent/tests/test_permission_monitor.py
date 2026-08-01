"""L0 -- PermissionMonitor: tracks Calls/Notes provider health and reports
only transitions into failure, so a periodic re-check doesn't spam a
notification every interval while a permission stays broken."""
from agent.permission_monitor import PermissionMonitor
from agent.tests.conftest import FakeCallsProvider, FakeNotesProvider


def _monitor(calls_provider=None, notes_provider=None) -> PermissionMonitor:
    return PermissionMonitor(
        calls_provider or FakeCallsProvider(),
        notes_provider or FakeNotesProvider(),
    )


class TestPermissionMonitor:
    def test_positiv_alles_gesund_keine_benachrichtigung(self):
        monitor = _monitor()
        notified: list[tuple[str, str]] = []

        monitor.check("en", lambda title, message: notified.append((title, message)))

        assert notified == []

    def test_positiv_telefonzugriff_verloren_beim_ersten_check_wird_gemeldet(self):
        """A permission already broken at the very first check (e.g. agent
        startup) must still notify -- not only on a later transition."""
        calls = FakeCallsProvider(phone_accessible=False, whatsapp_accessible=True)
        monitor = _monitor(calls_provider=calls)
        notified: list[tuple[str, str]] = []

        monitor.check("en", lambda title, message: notified.append((title, message)))

        assert len(notified) == 1
        assert "phone call history" in notified[0][1]

    def test_positiv_kein_erneutes_melden_solange_weiterhin_kaputt(self):
        calls = FakeCallsProvider(phone_accessible=False)
        monitor = _monitor(calls_provider=calls)
        notified: list[tuple[str, str]] = []
        notify = lambda title, message: notified.append((title, message))

        monitor.check("en", notify)
        monitor.check("en", notify)
        monitor.check("en", notify)

        assert len(notified) == 1

    def test_positiv_erneutes_melden_nach_erholung_und_erneutem_ausfall(self):
        calls = FakeCallsProvider(phone_accessible=False)
        monitor = _monitor(calls_provider=calls)
        notified: list[tuple[str, str]] = []
        notify = lambda title, message: notified.append((title, message))

        monitor.check("en", notify)
        calls._phone_accessible = True
        monitor.check("en", notify)  # recovered -- no new notification
        calls._phone_accessible = False
        monitor.check("en", notify)  # broke again -- notifies again

        assert len(notified) == 2

    def test_positiv_whatsapp_und_telefon_unabhaengig_gemeldet(self):
        calls = FakeCallsProvider(phone_accessible=False, whatsapp_accessible=False)
        monitor = _monitor(calls_provider=calls)
        notified: list[tuple[str, str]] = []

        monitor.check("en", lambda title, message: notified.append((title, message)))

        assert len(notified) == 2
        messages = [m for _, m in notified]
        assert any("phone call history" in m for m in messages)
        assert any("WhatsApp" in m for m in messages)

    def test_positiv_notizen_zugriff_verloren_wird_gemeldet(self):
        notes = FakeNotesProvider(healthy=False)
        monitor = _monitor(notes_provider=notes)
        notified: list[tuple[str, str]] = []

        monitor.check("en", lambda title, message: notified.append((title, message)))

        assert len(notified) == 1
        assert "Notes" in notified[0][1]

    def test_positiv_deutsche_uebersetzung(self):
        calls = FakeCallsProvider(phone_accessible=False)
        monitor = _monitor(calls_provider=calls)
        notified: list[tuple[str, str]] = []

        monitor.check("de", lambda title, message: notified.append((title, message)))

        assert len(notified) == 1
        assert "Rapport Agent" == notified[0][0]
        assert "Anrufliste" in notified[0][1]

    def test_negativ_health_wirft_exception_wird_nicht_als_kaputt_gewertet(self):
        class BrokenCallsProvider(FakeCallsProvider):
            def health(self):
                raise RuntimeError("boom")

        monitor = _monitor(calls_provider=BrokenCallsProvider())
        notified: list[tuple[str, str]] = []

        monitor.check("en", lambda title, message: notified.append((title, message)))

        assert notified == []
