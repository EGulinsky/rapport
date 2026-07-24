"""L0 — _select_files_to_keep() (routers/backup.py): grandfather-father-son
retention replacing the old flat "keep newest N" scheme, which only ever
gave a recovery window of N * backup-frequency (7 hourly backups = 7 hours —
far too short to recover from a mistake noticed a day or more later, as a
real production incident demonstrated)."""
import datetime
import pathlib

from agent.routers.backup import _select_files_to_keep


def _mtime(days_ago: float) -> float:
    now = datetime.datetime(2026, 7, 24, 12, 0, 0)
    return (now - datetime.timedelta(days=days_ago)).timestamp()


def _path(name: str) -> pathlib.Path:
    return pathlib.Path(f"/backups/{name}")


class TestHourlyTier:
    def test_positiv_behaelt_nur_die_neuesten_keep_hourly(self):
        files = [(_path(f"b{i}"), _mtime(i / 24)) for i in range(10)]

        keep = _select_files_to_keep(files, keep_hourly=3, keep_daily=0, keep_weekly=0)

        assert keep == {_path("b0"), _path("b1"), _path("b2")}


class TestDailyTier:
    def test_positiv_behaelt_ein_backup_pro_tag_darueber_hinaus(self):
        # 3 backups today (hours 0/1/2 ago), then one per day going back 5 days
        files = [(_path("h0"), _mtime(0)), (_path("h1"), _mtime(1 / 24)), (_path("h2"), _mtime(2 / 24))]
        for d in range(1, 6):
            files.append((_path(f"d{d}"), _mtime(d)))

        keep = _select_files_to_keep(files, keep_hourly=2, keep_daily=3, keep_weekly=0)

        # hourly tier: h0, h1 (2 newest), daily tier picks up h2's day plus
        # the next 2 distinct days among the remainder
        assert _path("h0") in keep and _path("h1") in keep
        assert len(keep) == 2 + 3

    def test_negativ_mehrere_backups_am_selben_tag_zaehlen_nur_einmal(self):
        files = [
            (_path("old"), _mtime(10)),
            (_path("same_day_a"), _mtime(3)),
            (_path("same_day_b"), _mtime(3.4)),
        ]

        keep = _select_files_to_keep(files, keep_hourly=0, keep_daily=1, keep_weekly=0)

        assert len(keep) == 1


class TestWeeklyTier:
    def test_positiv_behaelt_ein_backup_pro_woche_jenseits_der_tages_stufe(self):
        files = [(_path("recent"), _mtime(1))]
        for w in range(1, 6):
            files.append((_path(f"w{w}"), _mtime(w * 8)))  # ~8 days apart -> distinct ISO weeks

        keep = _select_files_to_keep(files, keep_hourly=1, keep_daily=1, keep_weekly=2)

        assert _path("recent") in keep
        assert len(keep) == 1 + 1 + 2

    def test_negativ_backups_jenseits_aller_stufen_werden_nicht_behalten(self):
        files = [(_path("ancient"), _mtime(400))]

        keep = _select_files_to_keep(files, keep_hourly=0, keep_daily=0, keep_weekly=0)

        assert keep == set()


class TestBackwardCompatibleDefaults:
    def test_positiv_alte_flache_semantik_bleibt_ueber_keep_hourly_moeglich(self):
        files = [(_path(f"b{i}"), _mtime(i / 24)) for i in range(10)]

        keep = _select_files_to_keep(files, keep_hourly=3, keep_daily=0, keep_weekly=0)

        assert len(keep) == 3
