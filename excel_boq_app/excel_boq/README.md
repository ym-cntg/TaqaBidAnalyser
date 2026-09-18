# Excel BOQ Extractor

Takes a vendor's priced spreadsheet and produces a normalized bill of
quantities: one flat, consistent line-item table plus an extraction
report.

This is a standalone feature branch (`excel-upload-feat`), separate from
the Maximo-backed comparison app. It does not read from or write to
Databricks, Unity Catalog, or Maximo, and it needs no grant. Uploads are
parsed in memory and discarded, so there is no upload history.

## Why it exists

`CLAUDE.md` describes the manual process: bidders submit Excel, the
analyst copies every price into a consolidated comparison spreadsheet by
hand, then checks for unquoted items and arithmetic errors. This
automates the copy and the two checks.

## Using it

**Standalone app**: the deployable client-testing app one level up.
See [../README.md](../README.md).

**Web page in the main app**: `/excel-boq`, linked from the Projects
landing page.

**CLI**, for a folder of files without starting the app:

```bash
python -m excel_boq_app.excel_boq.cli data/power/AGPOWER/original/excel/*.xlsx
python -m excel_boq_app.excel_boq.cli <one file.xlsx> --xlsx out.xlsx --json out.json
```

**API**:

| Endpoint | Returns |
|---|---|
| `POST /api/excel-boq/parse` | the extracted BOQ as JSON |
| `POST /api/excel-boq/export` | the normalized `.xlsx` workbook |

Both take a single multipart `file`. Limits: `.xlsx`/`.xlsm` only, 25MB.
Legacy `.xls` and PDF submissions are rejected with a clear message.

**Tests**: `python -m tests.test_excel_boq`, which runs against the real
files in `data/`.

## What it handles

Nothing keys off a fixed row or column. The header row is found by
scoring, and columns are mapped by keyword, so both sample layouts work
without configuration:

| | Columns | Header |
|---|---|---|
| ADDC power template | Item, Description, Unit, Est Qty, CIF unit rate + total, Erection unit rate + total, Total | two merged rows |
| Water bill template | Sl.No, Description, Unit, Quantity, Unit rate, Total line cost | one row |

Both collapse into one canonical line shape, so anything downstream
never has to branch on which template a vendor used.

Row classification matters as much as column mapping. Each row becomes
an `item` (priced, has a quantity), a `section` (a numbered heading),
a `subtotal` (a stated total restating rows above it), or a `note`.
Only `item` rows count toward any total. Getting this wrong is the
easiest way to silently double a contract value: on the sample power
file, counting subtotal rows inflated the total from 66.2M to 233M.

## The reconciliation check

The most useful output. The extracted line-item total is compared
against the vendor's own summary sheet, and a gap over 0.5% is
reported.

On the 105 sample files, 81 of the 83 that have a summary sheet
reconcile exactly. The two that do not are the same vendor file across
two rounds, and the mismatch is real: their Final Summary shows 0.00 for
items 3 through 8 while their detail sheets carry 22.5M of priced work.
That is the error class this check exists to catch.

Where a workbook has nested summaries (the water template has a project
summary plus one per area), the top-level one is used, not the sum,
which would double-count.

## Known limitations

- **`.xlsx`/`.xlsm` only.** No `.xls`, and no PDF; PDF extraction is
  still the unbuilt part of the original business case.
- **Formula cells are read as their cached value** (`data_only=True`).
  A file saved by a tool that did not compute formulas will show blanks
  where a formula was never evaluated.
- **Nothing is persisted.** No upload history, no link to an RFQ or a
  project, and no comparison across vendors. This extracts one file at a
  time; consolidating several vendors into one comparison is the
  obvious next step and is not built.
- **Lot structure is not inferred.** Sheets are kept separate and named
  as they are in the source; there is no lot-level rollup, matching the
  main app's existing limitation.
- **Section detection is heuristic**: a numbered row with no money, a
  description under 150 characters, and not an ADDC "No BOQ Item"
  placeholder. A vendor who writes a long heading gets it recorded as a
  note instead.
