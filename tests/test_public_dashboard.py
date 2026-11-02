"""Ensure Pages can NEVER include unreviewed macro or market observations."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/prepare_public_dashboard.py"
spec = importlib.util.spec_from_file_location("prepare_public_dashboard", SOURCE)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class PublicDashboardTests(unittest.TestCase):
    @staticmethod
    def make_dataset(root):
        (root / "series").mkdir(parents=True)
        sources = [
            ("valuation.world.listed_market_cap_usd", "cc_by_4_0", "501"),
            ("valuation.global.cape", "review_required", "PROPRIETARY_VALUE_NOT_ALLOWED"),
        ]
        items = []
        for sid, rights, value in sources:
            document = {
                "schema_version": 1, "id": sid, "name": sid, "theme": "valuation",
                "provider": "TEST", "geography": "WORLD",
                "frequency": "A", "unit": "ratio", "source_url": "https://example.org",
                "source_key": sid, "measurement": "Test", "rights": rights,
                "revision_policy": "revisable", "notes": "Test",
                "observations": [{"date": "2020-01-01", "value": value}],
            }
            (root / "series" / f"{sid}.json").write_text(json.dumps(document))
            items.append({
                "id": sid, "name": sid, "theme": "valuation", "provider": "TEST",
                "geography": "WORLD", "frequency": "A", "unit": "ratio",
                "source_url": "https://example.org",
                "rights": rights, "file": f"series/{sid}.json",
                "count": 1, "first": "2020-01-01", "last": "2020-01-01",
            })
        (root / "index.json").write_text(json.dumps({
            "schema_version": 1, "series_count": len(items), "series": items,
            "market": {"instrument_count": 24, "secret": "NOT_PUBLISHABLE"},
            "supplementary_sources": [{"secret": "WIESHEETS_SHOULD_NOT_BE_HERE"}],
            "generated_at_utc": "2026-11-02T01:02:03Z",
        }))
        (root / "charts.json").write_text(json.dumps({
            "schema_version": 1, "charts": [{
                "id": "private_chart", "title": "Restricted source",
                "status": "mapped", "theme": "valuation",
                "series_ids": ["valuation.global.cape"],
                "display_mode": "raw", "rationale": "Test", "caveats": "Private",
            }],
        }))
        (root / "markets").mkdir()
        (root / "markets" / "secret.json").write_text("NOT_PUBLISHABLE")
        (root / "fx").mkdir()
        (root / "fx" / "EUR.json").write_text("NOT_PUBLISHABLE")
        (root / "supplementary").mkdir()
        (root / "supplementary" / "data.json").write_text("NOT_PUBLISHABLE")

    def test_public_export_includes_only_confirmed_license_and_chart_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "private"
            out = Path(tmp) / "public"
            self.make_dataset(inp)
            manifest = module.prepare_public(inp, out)
            self.assertTrue(manifest["public_dataset"])
            self.assertEqual(manifest["series_count"], 1)
            self.assertEqual([x["id"] for x in manifest["series"]],
                             ["valuation.world.listed_market_cap_usd"])
            self.assertTrue((out / "series/valuation.world.listed_market_cap_usd.json").exists())
            self.assertFalse((out / "series/valuation.global.cape.json").exists())
            self.assertFalse((out / "markets").exists())
            self.assertFalse((out / "fx").exists())
            self.assertFalse((out / "supplementary").exists())
            merged = "\n".join(f.read_text() for f in out.rglob("*.json"))
            self.assertNotIn("PROPRIETARY_VALUE_NOT_ALLOWED", merged)
            self.assertNotIn("WIESHEETS_SHOULD_NOT_BE_HERE", merged)
            self.assertNotIn("NOT_PUBLISHABLE", merged)
            self.assertEqual(len(json.loads((out / "charts.json").read_text())["charts"]), 1)

    def test_fails_closed_on_rights_field_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "private"
            self.make_dataset(inp)
            doc = inp / "series/valuation.world.listed_market_cap_usd.json"
            content = json.loads(doc.read_text())
            content["rights"] = "review_required"
            doc.write_text(json.dumps(content))
            with self.assertRaisesRegex(ValueError, "Unverified published source"):
                module.prepare_public(inp, Path(tmp) / "public")
            self.assertFalse((Path(tmp) / "public").exists())

    def test_refuses_unknown_chart_series_before_any_file_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "private"
            self.make_dataset(inp)
            path = inp / "charts.json"
            o = json.loads(path.read_text())
            o["charts"][0]["series_ids"] = ["forged.private.series"]
            path.write_text(json.dumps(o))
            with self.assertRaisesRegex(ValueError, "Unknown chart source"):
                module.prepare_public(inp, Path(tmp) / "public")

    def test_refuses_no_redistributable_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "private"
            self.make_dataset(inp)
            path = inp / "index.json"
            obj = json.loads(path.read_text())
            for item in obj["series"]:
                item["rights"] = "review_required"
            path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "No positively licensed"):
                module.prepare_public(inp, Path(tmp) / "public")

if __name__ == "__main__":
    unittest.main()
