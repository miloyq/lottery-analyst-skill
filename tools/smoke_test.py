"""Offline CLI integration test. Synthetic data stays in a temporary database."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_lottery import fixture
from lottery.storage import Store


def main():
    passed = 0
    with tempfile.TemporaryDirectory(prefix="lottery smoke ") as tmp:
        work = Path(tmp) / "test data"
        work.mkdir()
        db = work / "synthetic.sqlite3"
        cli = ROOT / "lottery-analyst" / "scripts" / "lottery_cli.py"

        def call(*args, expected=0):
            nonlocal passed
            proc = subprocess.run([sys.executable, str(cli), "--db", str(db), *args],
                                  cwd=work, capture_output=True, encoding="utf-8", timeout=30)
            result = json.loads(proc.stdout if proc.returncode == 0 else proc.stderr)
            if proc.returncode != expected:
                raise RuntimeError((args, proc.returncode, result))
            passed += 1
            return result

        store = Store(db)
        try:
            for game in ("ssq", "dlt"):
                store.ingest(game, fixture(game), {"source": "SYNTHETIC_TEST_ONLY"})
        finally:
            store.close()

        for game in ("ssq", "dlt"):
            latest = fixture(game)[-1]
            assert call("stats", "--game", game, "--window", "30")["n"] == 30
            record_ids = []
            for mode in ("uniform", "constrained", "diverse"):
                result = call("generate", "--game", game, "--target", "2025041",
                              "--mode", mode, "--seed", "42")
                assert len(result["tickets"]) == 5
                record_ids.append(result["recommendation_id"])
            result = call("check", "--game", game, "--issue", latest["issue"],
                          "--front", *map(str, latest["front"]), "--back", *map(str, latest["back"]))
            assert result["tier"] == 1
            result = call("backtest", "--game", game, "--mode", "constrained", "--warmup", "30")
            assert len(result["folds"]) == 10
            call("review", "--id", str(record_ids[0]), expected=2)
            store = Store(db)
            try:
                store.ingest(game, fixture(game, 41)[-1:], {"source": "SYNTHETIC_TEST_ONLY"})
            finally:
                store.close()
            assert len(call("review", "--id", str(record_ids[0]))["results"]) == 5
            call("generate", "--game", game, "--target", latest["issue"], expected=2)
        assert len(call("records")) == 6
    print(json.dumps({"commands_passed": passed, "dataset": "SYNTHETIC_TEST_ONLY", "network": False}))


if __name__ == "__main__":
    main()
