"""L1 — files router gegen ein echtes tmp_path-Verzeichnis (reine
Dateisystem-Operationen, OS-neutral, keine Provider-Mocks nötig)."""


class TestListFiles:
    def test_positiv_findet_unterstuetzte_dateien(self, client, auth_headers, tmp_path):
        (tmp_path / "doc.txt").write_text("hallo welt")
        (tmp_path / "ignoriert.exe").write_text("bin")

        resp = client.get("/files", params={"folder": str(tmp_path)}, headers=auth_headers)

        assert resp.status_code == 200
        names = [f["name"] for f in resp.json()]
        assert names == ["doc.txt"]

    def test_positiv_subfolder_wird_erkannt(self, client, auth_headers, tmp_path):
        sub = tmp_path / "Firma XY"
        sub.mkdir()
        (sub / "anschreiben.txt").write_text("hi")

        resp = client.get("/files", params={"folder": str(tmp_path)}, headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()[0]["subfolder"] == "Firma XY"

    def test_negativ_ordner_existiert_nicht(self, client, auth_headers):
        resp = client.get("/files", params={"folder": "/nicht/vorhanden"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_corner_case_since_filter(self, client, auth_headers, tmp_path):
        (tmp_path / "alt.txt").write_text("x")
        import time
        future = time.time() + 100

        resp = client.get("/files", params={"folder": str(tmp_path), "since": future}, headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == []


class TestBrowse:
    def test_positiv_listet_dateien_und_ordner(self, client, auth_headers, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "Unterordner").mkdir()

        resp = client.get("/files/browse", params={"folder": str(tmp_path)}, headers=auth_headers)

        assert resp.status_code == 200
        types = {item["name"]: item["type"] for item in resp.json()}
        assert types == {"a.txt": "file", "Unterordner": "folder"}

    def test_negativ_unterordner_existiert_nicht(self, client, auth_headers, tmp_path):
        resp = client.get(
            "/files/browse", params={"folder": str(tmp_path), "subfolder": "fehlt"}, headers=auth_headers
        )
        assert resp.status_code == 400


class TestGetFile:
    def test_positiv_liefert_textinhalt(self, client, auth_headers, tmp_path):
        f = tmp_path / "notiz.txt"
        f.write_text("Testinhalt")

        resp = client.get("/files/file", params={"path": str(f)}, headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["text"] == "Testinhalt"

    def test_negativ_datei_existiert_nicht(self, client, auth_headers):
        resp = client.get("/files/file", params={"path": "/nicht/da.txt"}, headers=auth_headers)
        assert resp.status_code == 404


class TestOpenAndPickers:
    def test_positiv_open_ruft_provider_auf(self, client, auth_headers, fake_files_provider, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("x")

        resp = client.post("/files/open", json={"path": str(f)}, headers=auth_headers)

        assert resp.status_code == 200
        assert fake_files_provider.opened_paths == [str(f)]

    def test_negativ_open_datei_existiert_nicht(self, client, auth_headers):
        resp = client.post("/files/open", json={"path": "/nicht/da.txt"}, headers=auth_headers)
        assert resp.status_code == 404

    def test_positiv_pick_folder_liefert_provider_ergebnis(self, client, auth_headers, fake_files_provider):
        resp = client.get("/files/pick-folder", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["path"] == fake_files_provider.picked_folder

    def test_negativ_pick_folder_abgebrochen(self, client, auth_headers, fake_files_provider):
        fake_files_provider.picked_folder = None

        resp = client.get("/files/pick-folder", headers=auth_headers)

        assert resp.status_code == 400

    def test_positiv_pick_file_liefert_provider_ergebnis(self, client, auth_headers, fake_files_provider):
        resp = client.get("/files/pick-file", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["path"] == fake_files_provider.picked_file
