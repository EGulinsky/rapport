"""L0 Unit — _imap_fetch_full_bytes() in sync_icloud.py.

Regression coverage for a real production bug: iCloud's IMAP server
silently returned an EMPTY fetch response ("<seq> ()") for the RFC822
macro on a message that RFC822.SIZE/FLAGS/HEADER all reported as present
and non-empty (8238 bytes) -- while BODY.PEEK[] reliably returned the full
content for the same message. The old code (`data[0][1]`) didn't check
whether the response actually contained a tuple, so indexing the bare
`bytes` response silently returned an `int` (Python 3's bytes.__getitem__
on a single index) instead of raising -- surfacing downstream as a cryptic
"'int' object has no attribute 'decode'" rather than a clear error right
at the fetch site. This one bug meant iCloud Mail sync (bulk, per-app
targeted, and the manual "assign to application" flow) had never
successfully created a single event.
"""
import pytest

from app.routers.sync_icloud import _imap_fetch_full_bytes

pytestmark = pytest.mark.unit


class _FakeImap:
    def __init__(self, response):
        self._response = response
        self.fetch_calls: list[tuple] = []

    def fetch(self, msg_id_bytes, spec):
        self.fetch_calls.append((msg_id_bytes, spec))
        return ("OK", self._response)


class TestImapFetchFullBytes:
    def test_positiv_gibt_rohe_bytes_zurueck(self):
        imap = _FakeImap([(b"1 (BODY[] {10}", b"hello body")])

        result = _imap_fetch_full_bytes(imap, b"1")

        assert result == b"hello body"

    def test_positiv_nutzt_body_peek_nicht_rfc822(self):
        # BODY.PEEK[] doesn't mark the message \Seen, unlike RFC822/BODY[] --
        # confirmed as the reliable fetch item against production iCloud.
        imap = _FakeImap([(b"1 (BODY[] {10}", b"hello body")])

        _imap_fetch_full_bytes(imap, b"1")

        assert imap.fetch_calls == [(b"1", "(BODY.PEEK[])")]

    def test_negativ_leere_antwort_bytes_statt_tuple_wirft_klaren_fehler(self):
        # The exact malformed shape observed against production: the server
        # returns "<seq> ()" as a bare bytes response instead of a
        # (header, content) tuple.
        imap = _FakeImap([b"1 ()"])

        with pytest.raises(RuntimeError, match="keinen Inhalt"):
            _imap_fetch_full_bytes(imap, b"1")

    def test_negativ_leere_datenliste_wirft_klaren_fehler(self):
        imap = _FakeImap([])

        with pytest.raises(RuntimeError, match="keinen Inhalt"):
            _imap_fetch_full_bytes(imap, b"1")

    def test_negativ_kurzes_tuple_wirft_klaren_fehler(self):
        imap = _FakeImap([(b"1 (BODY[] {0}",)])

        with pytest.raises(RuntimeError, match="keinen Inhalt"):
            _imap_fetch_full_bytes(imap, b"1")
