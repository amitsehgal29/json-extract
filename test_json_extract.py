#!/usr/bin/env python3
import csv
import io
import json
import os
import tempfile
import unittest

import json_extract as jx


SAMPLES = os.path.join(os.path.dirname(__file__), "samples")
EVENTS = os.path.join(SAMPLES, "events.csv")


def run_main(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_out, old_err = jx.sys.stdout, jx.sys.stderr
    jx.sys.stdout, jx.sys.stderr = stdout, stderr
    try:
        code = jx.main(argv)
    finally:
        jx.sys.stdout, jx.sys.stderr = old_out, old_err
    err = stderr.getvalue()
    summary = json.loads(err) if err.strip().startswith("{") else None
    return code, stdout.getvalue(), summary, err


class HelperTests(unittest.TestCase):
    def test_parse_fields(self):
        self.assertEqual(
            jx.parse_fields("user.id:user_id,amount,items.0.sku:sku"),
            [("user.id", "user_id"), ("amount", "amount"), ("items.0.sku", "sku")],
        )

    def test_walk(self):
        data = {"user": {"id": "U1"}, "items": [{"sku": "A1"}]}
        self.assertEqual(jx.walk(data, ["user", "id"]), ("U1", True))
        self.assertEqual(jx.walk(data, ["items", 0, "sku"]), ("A1", True))
        self.assertEqual(jx.walk(data, ["items", 1, "sku"]), (None, False))
        self.assertEqual(jx.walk(data, ["amount"]), (None, False))


class CliTests(unittest.TestCase):
    def test_sample_run(self):
        code, out, summary, _err = run_main(
            [
                EVENTS,
                "--column",
                "payload",
                "--fields",
                "user.id:user_id,amount,items.0.sku:sku",
                "--max-unparseable",
                "1",
            ]
        )
        self.assertEqual(code, 0)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["extracted"], 3)
        self.assertEqual(summary["unparseable"], 1)
        self.assertEqual(summary["missing"]["sku"], 2)  # e2 empty list, e4 no items
        self.assertEqual(summary["missing"]["amount"], 1)  # e4
        rows = list(csv.DictReader(io.StringIO(out)))
        self.assertEqual(rows[0]["user_id"], "U1")
        self.assertEqual(rows[0]["amount"], "50.0")
        self.assertEqual(rows[0]["sku"], "A1")
        self.assertEqual(rows[1]["user_id"], "U2")
        self.assertEqual(rows[1]["sku"], "")
        self.assertEqual(rows[2]["user_id"], "")
        self.assertEqual(rows[3]["user_id"], "U3")
        self.assertEqual(rows[3]["amount"], "")

    def test_unparseable_exits_one(self):
        code, _out, summary, _err = run_main(
            [EVENTS, "--column", "payload", "--fields", "user.id:user_id"]
        )
        self.assertEqual(code, 1)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["unparseable"], 1)

    def test_drop_column_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "out.csv")
            code, out, summary, _err = run_main(
                [
                    EVENTS,
                    "--column",
                    "payload",
                    "--fields",
                    "user.id:user_id",
                    "--drop-column",
                    "--write",
                    dest,
                    "--max-unparseable",
                    "1",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            with open(dest, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(list(rows[0].keys()), ["event_id", "user_id"])
            self.assertEqual(rows[0]["user_id"], "U1")

    def test_missing_column_exits_two(self):
        code, _out, summary, err = run_main(
            [EVENTS, "--column", "nope", "--fields", "user.id"]
        )
        self.assertEqual(code, 2)
        self.assertIsNone(summary)
        self.assertIn("missing column", err)

    def test_nested_object_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rows.csv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write('id,payload\n1,"{""user"":{""id"":""U1"",""city"":""DXB""}}"\n')
            code, out, summary, _err = run_main(
                [path, "--column", "payload", "--fields", "user"]
            )
            self.assertEqual(code, 0)
            rows = list(csv.DictReader(io.StringIO(out)))
            self.assertEqual(json.loads(rows[0]["user"]), {"id": "U1", "city": "DXB"})


if __name__ == "__main__":
    unittest.main()
