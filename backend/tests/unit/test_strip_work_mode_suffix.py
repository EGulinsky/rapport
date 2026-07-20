"""L0 Unit — _strip_work_mode_suffix() in routers/applications.py.
LinkedIn appends "(On-site)"/"(Hybrid)"/"(Remote)" to every job's location
on import -- confirmed against production data that neither Nominatim nor
Google's Geocoding API can resolve an address with that suffix still
attached (e.g. "Krefeld (Hybrid)" returns zero results, plain "Krefeld"
geocodes fine), so _geocode_ort()/backfill_ort_geocode() strip it first.
"""
import pytest

from app.routers.applications import _strip_work_mode_suffix

pytestmark = pytest.mark.unit


class TestStripWorkModeSuffix:
    @pytest.mark.parametrize("suffix", ["On-site", "Onsite", "Hybrid", "Remote", "REMOTE", "hybrid"])
    def test_positiv_entfernt_bekannte_suffixe(self, suffix):
        assert _strip_work_mode_suffix(f"Krefeld ({suffix})") == "Krefeld"

    def test_positiv_mehrteiliger_ortsname_bleibt_erhalten(self):
        assert _strip_work_mode_suffix("Baden-Württemberg, Germany (On-site)") == "Baden-Württemberg, Germany"

    def test_negativ_ohne_suffix_unveraendert(self):
        assert _strip_work_mode_suffix("München, Deutschland") == "München, Deutschland"

    def test_negativ_klammer_nicht_am_ende_bleibt_erhalten(self):
        # A parenthetical that isn't a recognized work-mode tag, or isn't at
        # the very end of the string, is left alone -- only strip what we're
        # sure is LinkedIn's own suffix format.
        assert _strip_work_mode_suffix("Musterstadt (Bayern)") == "Musterstadt (Bayern)"
