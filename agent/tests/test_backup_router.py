"""L1 — backup router: Schreiben/Lesen/Rotation gegen ein echtes tmp_path."""
import base64


class TestBackupWriteReadRoundtrip:
    def test_positiv_write_read_roundtrip(self, client, auth_headers, tmp_path):
        data_b64 = base64.b64encode(b"hallo welt").decode()

        write_resp = client.post(
            "/backup/backup-write",
            json={"folder": str(tmp_path), "filename": "test.zip", "data_b64": data_b64, "keep_count": 7},
            headers=auth_headers,
        )
        assert write_resp.status_code == 200

        list_resp = client.get("/backup/backups", params={"folder": str(tmp_path)}, headers=auth_headers)
        assert [b["name"] for b in list_resp.json()] == ["test.zip"]

        read_resp = client.get(
            "/backup/backup-read", params={"path": str(tmp_path / "test.zip")}, headers=auth_headers
        )
        assert base64.b64decode(read_resp.json()["data_b64"]) == b"hallo welt"

    def test_positiv_rotation_behaelt_nur_neueste_keep_count(self, client, auth_headers, tmp_path):
        import time

        for i in range(5):
            client.post(
                "/backup/backup-write",
                json={
                    "folder": str(tmp_path), "filename": f"backup_{i}.zip",
                    "data_b64": base64.b64encode(b"x").decode(), "keep_count": 3,
                },
                headers=auth_headers,
            )
            time.sleep(0.01)

        list_resp = client.get("/backup/backups", params={"folder": str(tmp_path)}, headers=auth_headers)
        assert len(list_resp.json()) == 3

    def test_negativ_fehlende_felder_400(self, client, auth_headers, tmp_path):
        resp = client.post(
            "/backup/backup-write",
            json={"folder": str(tmp_path), "filename": "", "data_b64": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_negativ_backup_read_datei_fehlt(self, client, auth_headers, tmp_path):
        resp = client.get(
            "/backup/backup-read", params={"path": str(tmp_path / "fehlt.zip")}, headers=auth_headers
        )
        assert resp.status_code == 404

    def test_corner_case_backups_liste_bei_fehlendem_ordner_leer(self, client, auth_headers):
        resp = client.get("/backup/backups", params={"folder": "/nicht/vorhanden"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_negativ_nicht_backup_dateien_werden_ignoriert(self, client, auth_headers, tmp_path):
        (tmp_path / "notiz.txt").write_text("x")
        resp = client.get("/backup/backups", params={"folder": str(tmp_path)}, headers=auth_headers)
        assert resp.json() == []
