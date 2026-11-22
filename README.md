# json-extract

Pull dotted JSON paths out of a CSV column into new columns. Each row's JSON object is walked with paths such as `user.id` or `items.0.sku` (dots separate keys; integer segments are list indexes). Missing paths are left blank; invalid JSON is counted as unparseable. Python 3 standard library only.

Use it to flatten a semi-structured payload column in a landing file before loading a table. It complements `jsonl-flatten`, which expands a whole JSON Lines file rather than selected paths from one CSV column.

## Usage

```bash
python3 json_extract.py samples/events.csv \
  --column payload --fields user.id:user_id,amount,items.0.sku:sku --max-unparseable 1
```

The CSV is written to stdout. A JSON summary is written to stderr. Use `--write out.csv` to write the CSV to a file.

Options:

- `--column payload` the column that holds a JSON object (as a string).
- `--fields user.id:user_id,amount,items.0.sku:sku` paths to extract. A `:alias` renames the output column; without an alias the path is used as the name.
- `--drop-column` omits the original JSON column from the output.
- `--max-unparseable 0` (default) is how many invalid or empty JSON cells are allowed before exit 1.

Objects and arrays that are themselves selected are written as compact JSON. Booleans are written as `true`/`false`.

Exit codes: `0` unparseable cells within the cap, `1` too many unparseable cells, `2` bad input.

## Example output (real run on the samples)

Stdout:

```csv
event_id,payload,user_id,amount,sku
e1,"{""user"": {""id"": ""U1""}, ""amount"": 50.0, ""items"": [{""sku"": ""A1""}, {""sku"": ""A2""}]}",U1,50.0,A1
e2,"{""user"": {""id"": ""U2""}, ""amount"": 20, ""items"": []}",U2,20,
e3,not-json,,,
e4,"{""user"": {""id"": ""U3""}}",U3,,
```

Stderr:

```json
{
  "rows": 4,
  "column": "payload",
  "fields": [
    {"path": "user.id", "column": "user_id"},
    {"path": "amount", "column": "amount"},
    {"path": "items.0.sku", "column": "sku"}
  ],
  "extracted": 3,
  "unparseable": 1,
  "missing": {"user_id": 0, "amount": 1, "sku": 2},
  "unparseable_examples": [{"line": 3, "reason": "invalid_json"}],
  "written": "-",
  "ok": true
}
```

(The stderr JSON was reformatted slightly for width. Exit code was 0 because of `--max-unparseable 1`.)

e1 gets `U1`, `50.0`, and the first item SKU `A1`. e2 has an empty items list so `sku` is blank. e3 is invalid JSON. e4 has no amount or items.

## Tests

```bash
python3 -m unittest -v
```
