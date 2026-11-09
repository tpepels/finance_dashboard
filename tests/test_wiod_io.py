"""WIOD 2016 input-output tables: productive/unproductive totals under the authors' rule."""
import unittest

from finance_dashboard.wiod_io import table_aggregates


def table():
    # Two countries, three industries: P1, P2 productive, U1 unproductive.
    codes = ["", "", "", "", "P1", "P2", "U1", "P1", "P2", "U1", "CONS_h", "GO"]
    countries = ["", "", "", "", "AAA", "AAA", "AAA", "BBB", "BBB", "BBB", "AAA", "TOT"]
    def row(code, country, values):
        return [code, code, country, "r"] + values + [0.0, 0.0]
    body = [row("P1", "AAA", [10, 2, 1, 3, 0, 0]), row("P2", "AAA", [1, 5, 2, 0, 0, 0]), row("U1", "AAA", [4, 1, 3, 0, 0, 1]),
            row("P1", "BBB", [2, 0, 0, 7, 1, 1]), row("P2", "BBB", [0, 0, 0, 1, 4, 0]), row("U1", "BBB", [0, 0, 0, 2, 0, 2])]
    totals = [["TXSP", "taxes", "TOT", "r66", 1, 2, 0.5, 0, 0, 0, 0, 0], ["GO", "output", "TOT", "r73", 100, 50, 40, 60, 30, 20, 0, 0]]
    return [["title"], ["sub"], codes, ["names"], countries, ["c"]] + body + totals


class TableAggregateTests(unittest.TestCase):
    def test_totals_follow_the_published_rule(self):
        cls = {"P1": "PA", "P2": "PA", "U1": "UA.finance"}
        out = table_aggregates(table(), cls)
        aaa = out["AAA"]
        # TV.PA = GO + product taxes of productive columns; inputs from productive rows of every country count.
        self.assertEqual(aaa["TV.PA"], 100 + 50 + 1 + 2)
        self.assertEqual(aaa["VA.PA"], 153 - (10 + 2 + 1 + 5 + 2 + 0))
        self.assertEqual(aaa["GI.UA"], 40 + 0.5)
        self.assertEqual(aaa["NI.UA"], 40.5 - 3)
        self.assertEqual(out["BBB"]["TV.PA"], 90)


if __name__ == "__main__":
    unittest.main()


class StoreTests(unittest.TestCase):
    def test_only_the_publishers_bytes_are_archived(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from finance_dashboard import wiod_io
        from finance_dashboard.bis import ProviderError
        with TemporaryDirectory() as temp:
            original = Path(temp) / "WIOTS_in_EXCEL.zip"
            original.write_bytes(b"not the tables")
            with self.assertRaises(ProviderError):
                wiod_io.store_wiod_tables(original, Path(temp) / "evidence")
            from hashlib import sha1
            pin = {**wiod_io.PIN, "bytes": len(b"not the tables"), "sha1": sha1(b"not the tables").hexdigest()}
            with patch.object(wiod_io, "PIN", pin):
                bundle = wiod_io.store_wiod_tables(original, Path(temp) / "evidence")
                self.assertEqual(wiod_io.store_wiod_tables(original, Path(temp) / "evidence"), bundle)
            self.assertEqual((bundle / "WIOTS_in_EXCEL.zip").read_bytes(), b"not the tables")
            self.assertTrue((bundle / "manifest.json").is_file())
