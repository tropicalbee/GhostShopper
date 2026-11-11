"""Bundled example checks: loaded once at startup as shared examples, with working screenshots and traces."""

import json

from fastapi.testclient import TestClient

from backend.app import db
from backend.app.config import Settings
from backend.app.examples import EXAMPLES_DIR, MANIFEST, SANDBOX_EMAIL_RE, load_examples
from backend.app.main import create_app


def deployed(tmp_path, **kw) -> Settings:
    return Settings("", "", tmp_path / "a.db", "https://ghostshopper.example", paypal_mode="mock",
                    runs_dir=tmp_path / "runs", frontend_dist=tmp_path / "dist", **kw)


def test_bundle_holds_no_local_paths_or_sandbox_emails():
    text = (EXAMPLES_DIR / MANIFEST).read_text(encoding="utf-8")
    assert "C:/" not in text and "/Users/" not in text
    assert all(m.group(0).startswith("sb-redacted@") for m in SANDBOX_EMAIL_RE.finditer(text))


def test_bundle_holds_no_sandbox_payer_ids_or_shipping_address():
    text = (EXAMPLES_DIR / MANIFEST).read_text(encoding="utf-8")
    for leaked in ("QBQXTNZKDC68C", "ZQ5RDYQCFMK3W", "2211 N First St"):
        assert leaked not in text


def test_examples_load_once_as_shared_runs(tmp_path):
    db.init_db(tmp_path / "a.db")
    bundled = json.loads((EXAMPLES_DIR / MANIFEST).read_text(encoding="utf-8"))
    added = load_examples(tmp_path / "a.db", tmp_path / "runs")
    assert len(added) == len(bundled) >= 2
    assert load_examples(tmp_path / "a.db", tmp_path / "runs") == []  # already there: nothing new
    with db.connect(tmp_path / "a.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs WHERE owner_hash IS NULL").fetchone()[0] == len(bundled)
        for run_id in added:
            paths = [r[0] for r in conn.execute("SELECT screenshot_path FROM steps WHERE run_id = ? AND screenshot_path IS NOT NULL", (run_id,))]
            assert paths and all(p.startswith((tmp_path / "runs" / f"run-{run_id}").as_posix()) for p in paths)


def test_a_deployed_server_shows_the_examples_to_any_visitor(tmp_path):
    app = create_app(deployed(tmp_path, example_runs=True))
    with TestClient(app, base_url="https://testserver") as c:
        runs = c.get("/api/runs").json()
        examples = [r for r in runs if r["example"]]
        assert {r["outcome"] for r in examples} == {"purchased"}
        scores = sorted(c.get(f"/api/runs/{r['id']}").json()["score"]["total"] for r in examples)
        assert scores == [49, 100]
        best = max(examples, key=lambda r: r["id"])
        run = c.get(f"/api/runs/{best['id']}").json()
        assert run["trace"]["stages"] and run["order"] is not None
        shot = run["steps"][0]["screenshot_path"].rsplit("/", 1)[-1]
        r = c.get(f"/api/runs/{best['id']}/files/{shot}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_examples_stay_off_unless_asked(tmp_path):
    with TestClient(create_app(deployed(tmp_path)), base_url="https://testserver") as c:
        assert c.get("/api/runs").json() == []
