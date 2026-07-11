"""L1 Unit — _commit_with_retry() und _split_headline() in sync_linkedin.py.
Reine Funktionen bzw. Funktionen mit einfach mockbaren Seiteneffekten."""
from unittest.mock import MagicMock

import pytest

from app.routers.sync_linkedin import _commit_with_retry, _split_headline

pytestmark = pytest.mark.unit


class TestCommitWithRetry:
    def test_positiv_erfolgreicher_commit_ohne_retry(self):
        db = MagicMock()

        _commit_with_retry(db)

        db.commit.assert_called_once()
        db.rollback.assert_not_called()

    def test_positiv_locked_fehler_wird_wiederholt_und_gelingt_dann(self, monkeypatch):
        db = MagicMock()
        db.commit.side_effect = [Exception("database is locked"), None]
        monkeypatch.setattr("app.routers.sync_linkedin.time.sleep", lambda s: None)

        _commit_with_retry(db, retries=3, delay=0.01)

        assert db.commit.call_count == 2
        db.rollback.assert_called_once()

    def test_negativ_dauerhaft_locked_wirft_nach_allen_versuchen(self, monkeypatch):
        db = MagicMock()
        db.commit.side_effect = Exception("database is locked")
        monkeypatch.setattr("app.routers.sync_linkedin.time.sleep", lambda s: None)

        with pytest.raises(Exception, match="locked"):
            _commit_with_retry(db, retries=2, delay=0.01)

        assert db.commit.call_count == 2

    def test_negativ_anderer_fehler_wird_sofort_durchgereicht(self):
        db = MagicMock()
        db.commit.side_effect = Exception("some other db error")

        with pytest.raises(Exception, match="some other db error"):
            _commit_with_retry(db, retries=5)

        assert db.commit.call_count == 1
        db.rollback.assert_not_called()


class TestSplitHeadline:
    def test_positiv_at_trennzeichen(self):
        assert _split_headline("Senior Engineer at Contoso") == ("Senior Engineer", "Contoso")

    def test_positiv_bei_trennzeichen(self):
        assert _split_headline("Senior Engineer bei Contoso") == ("Senior Engineer", "Contoso")

    def test_positiv_at_zeichen_trennzeichen(self):
        assert _split_headline("Senior Engineer @ Contoso") == ("Senior Engineer", "Contoso")

    def test_negativ_ohne_trennzeichen_alles_als_rolle(self):
        assert _split_headline("Head of Customer Program Management") == ("Head of Customer Program Management", None)

    def test_negativ_leerer_headline_liefert_none_none(self):
        assert _split_headline(None) == (None, None)
        assert _split_headline("") == (None, None)
