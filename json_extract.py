#!/usr/bin/env python3
"""json-extract: pull dotted JSON paths out of a CSV column into new columns.

Standard library only. Each row's JSON object (in one column) is walked with
paths such as user.id or items.0.sku, and the values are written as extra
CSV columns. Missing paths are left blank; invalid JSON is counted as
unparseable.
"""
import argparse
import csv
import json
import sys


def parse_fields(value):
    """Parse 'path' or 'path:alias' lists into [(path, alias), ...]."""
    fields = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            path, alias = part.split(":", 1)
            path, alias = path.strip(), alias.strip()
        else:
            path = alias = part
        if not path or not alias:
            raise ValueError(f"invalid field spec {part!r}")
        fields.append((path, alias))
    return fields


def parse_path(path):
    tokens = []
    for part in path.split("."):
        if part == "":
            raise ValueError(f"invalid path {path!r}")
        if part.isdigit():
            tokens.append(int(part))
        else:
            tokens.append(part)
    return tokens


def walk(data, tokens):
    current = data
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current) or token < 0:
                return None, False
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return None, False
            current = current[token]
    return current, True


def format_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def extract_rows(rows, column, fields):
    compiled = [(path, alias, parse_path(path)) for path, alias in fields]
    out_rows = []
    unparseable = []
    missing_counts = {alias: 0 for _path, alias, _tokens in compiled}
    extracted = 0
    for i, row in enumerate(rows, start=1):
        raw = row.get(column)
        out = dict(row)
        for _path, alias, _tokens in compiled:
            out[alias] = ""
        if raw is None or str(raw).strip() == "":
            unparseable.append({"line": i, "reason": "empty"})
            out_rows.append(out)
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            unparseable.append({"line": i, "reason": "invalid_json"})
            out_rows.append(out)
            continue
        extracted += 1
        for _path, alias, tokens in compiled:
            value, found = walk(data, tokens)
            if not found:
                missing_counts[alias] += 1
                out[alias] = ""
            else:
                out[alias] = format_value(value)
        out_rows.append(out)
    return out_rows, extracted, unparseable, missing_counts


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract dotted JSON paths from a CSV column into new columns."
    )
    parser.add_argument("path", help="CSV file")
    parser.add_argument("-c", "--column", required=True, help="column that holds a JSON object")
    parser.add_argument(
        "-f",
        "--fields",
        required=True,
        help="comma-separated paths, optionally aliased, e.g. user.id:user_id,amount,items.0.sku:sku",
    )
    parser.add_argument(
        "--drop-column",
        action="store_true",
        help="omit the original JSON column from the output",
    )
    parser.add_argument(
        "--write",
        metavar="OUT",
        help="write the CSV to OUT ('-' for stdout). Default: stdout",
    )
    parser.add_argument(
        "--max-unparseable",
        type=int,
        default=0,
        help="allowed unparseable JSON cells before exit 1 (default: 0)",
    )
    args = parser.parse_args(argv)

    try:
        fields = parse_fields(args.fields)
    except ValueError as exc:
        print(f"json-extract: {exc}", file=sys.stderr)
        return 2
    if not fields:
        print("json-extract: --fields is required", file=sys.stderr)
        return 2
    aliases = [alias for _path, alias in fields]
    if len(set(aliases)) != len(aliases):
        print("json-extract: duplicate output column names in --fields", file=sys.stderr)
        return 2

    try:
        with open(args.path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        print(f"json-extract: {exc}", file=sys.stderr)
        return 2

    if args.column not in fieldnames:
        print(f"json-extract: missing column {args.column!r}", file=sys.stderr)
        return 2
    collisions = [alias for alias in aliases if alias in fieldnames and alias != args.column]
    if collisions:
        print("json-extract: output column(s) already exist: " + ", ".join(collisions), file=sys.stderr)
        return 2

    try:
        out_rows, extracted, unparseable, missing_counts = extract_rows(
            rows, args.column, fields
        )
    except ValueError as exc:
        print(f"json-extract: {exc}", file=sys.stderr)
        return 2

    out_fields = [name for name in fieldnames if not (args.drop_column and name == args.column)]
    for alias in aliases:
        if alias not in out_fields:
            out_fields.append(alias)

    dest = args.write if args.write is not None else "-"
    try:
        if dest == "-":
            writer = csv.DictWriter(sys.stdout, fieldnames=out_fields, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(out_rows)
        else:
            with open(dest, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=out_fields, lineterminator="\n", extrasaction="ignore")
                writer.writeheader()
                writer.writerows(out_rows)
    except OSError as exc:
        print(f"json-extract: {exc}", file=sys.stderr)
        return 2

    report = {
        "rows": len(rows),
        "column": args.column,
        "fields": [{"path": path, "column": alias} for path, alias in fields],
        "extracted": extracted,
        "unparseable": len(unparseable),
        "missing": missing_counts,
        "unparseable_examples": unparseable[:10],
        "written": dest,
        "ok": len(unparseable) <= args.max_unparseable,
    }
    if not report["ok"]:
        report["failed_checks"] = [
            f"unparseable {len(unparseable)} > max-unparseable {args.max_unparseable}"
        ]
    print(json.dumps(report, indent=2), file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
