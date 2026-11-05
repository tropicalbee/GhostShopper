from backend.app.seed import bad_store_flaws, main
from store.flaws import CLASSIC_FLAWS, FlawStore


def test_seed_sets_the_bad_store_without_a_server(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "seed.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    FlawStore(db_path).set_many({k: True for k in bad_store_flaws()})
    assert main([]) == 0
    assert FlawStore(db_path).get_all() == {k: k in CLASSIC_FLAWS for k in bad_store_flaws()}
    out = capsys.readouterr().out
    assert "Server not reachable" in out and "Demo commands" in out


def test_recording_runs_needs_a_server(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "seed.db"))
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:9")
    assert main(["--with-runs"]) == 2
