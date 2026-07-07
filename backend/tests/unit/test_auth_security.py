"""L0 Unit — app/auth/security.py: Passwort-Hashing, JWT-Encode/Decode,
Bestätigungscode-Generierung. Reine Kryptographie-/Logik-Funktionen, keine DB.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth import security

pytestmark = pytest.mark.unit


class TestPasswordHashing:
    def test_positiv_gehashtes_passwort_wird_korrekt_verifiziert(self):
        hashed = security.hash_password("supersecret123")
        assert security.verify_password("supersecret123", hashed) is True

    def test_negativ_falsches_passwort_wird_abgelehnt(self):
        hashed = security.hash_password("supersecret123")
        assert security.verify_password("falschespasswort", hashed) is False

    def test_positiv_hash_enthaelt_niemals_das_klartext_passwort(self):
        hashed = security.hash_password("supersecret123")
        assert "supersecret123" not in hashed

    def test_corner_case_zwei_hashes_desselben_passworts_unterscheiden_sich(self):
        # bcrypt nutzt einen zufälligen Salt — identische Passwörter dürfen
        # nicht denselben Hash erzeugen (sonst wäre ein Rainbow-Table-Angriff möglich).
        h1 = security.hash_password("supersecret123")
        h2 = security.hash_password("supersecret123")
        assert h1 != h2
        assert security.verify_password("supersecret123", h1) is True
        assert security.verify_password("supersecret123", h2) is True


class TestAccessToken:
    def test_positiv_token_dekodiert_zur_richtigen_user_id(self):
        token = security.create_access_token(42)
        assert security.decode_access_token(token) == 42

    def test_negativ_manipuliertes_token_liefert_none(self):
        token = security.create_access_token(42)
        kaputt = token[:-4] + "abcd"
        assert security.decode_access_token(kaputt) is None

    def test_negativ_unsinniger_string_liefert_none(self):
        assert security.decode_access_token("kein-jwt-token") is None

    def test_negativ_abgelaufenes_token_liefert_none(self):
        expired_payload = {"sub": "42", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
        expired_token = jwt.encode(expired_payload, security._jwt_secret(), algorithm=security.JWT_ALGORITHM)
        assert security.decode_access_token(expired_token) is None

    def test_negativ_token_ohne_sub_claim_liefert_none(self):
        payload = {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
        token = jwt.encode(payload, security._jwt_secret(), algorithm=security.JWT_ALGORITHM)
        assert security.decode_access_token(token) is None


class TestVerificationCode:
    def test_positiv_code_ist_sechsstellig_numerisch(self):
        code = security.generate_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_corner_case_fuehrende_nullen_bleiben_erhalten(self):
        # secrets.randbelow(1_000_000) kann Werte < 100000 liefern — das Format
        # muss diese trotzdem auf 6 Stellen auffüllen, sonst kollidiert die
        # Code-Prüfung (String-Vergleich) mit einer kürzeren Nutzereingabe.
        codes = {security.generate_verification_code() for _ in range(200)}
        assert all(len(c) == 6 for c in codes)

    def test_positiv_ablaufzeit_liegt_in_der_zukunft(self):
        expiry = security.verification_code_expiry()
        assert expiry > datetime.now(timezone.utc)
        assert expiry <= datetime.now(timezone.utc) + timedelta(minutes=security.VERIFICATION_CODE_EXPIRE_MINUTES + 1)
