# TAQA Bid Analyzer Demo

## Project Overview
AI-driven commercial bid analysis tool for **TAQA / ADDC** (Abu Dhabi Distribution Company).
Automates extraction, comparison, and analysis of vendor bid documents for procurement tenders.

## Client
- **Organization**: TAQA / ADDC — Abu Dhabi power & water distribution utility
- **BU**: Procurement (Salem Abodirahm, Asim Hassan, Yaser Al Derei, Mariam Mohammed)
- **SME**: Mohammed Al Katheri (procurement analyst, power team)
- **Our team**: Shiladitya Biswas, Vanden Jain, Aleksandr Uvarov, Sunish Rajendran Narayanan

## Business Case
- ~2,812 bids/year, ~7 hours per bid manual analysis
- AI target: 40-80% time reduction on bid analysis
- 5-year impact: AED 8-36M savings, ROI 2-10x
- Upfront investment: AED 3.5M, annual OPEX saving: AED 0.3M

## Current Manual Process (from Mohammed Al Katheri)
1. Download bid offers from **Maximo (IBM)** portal
2. Bidders submit Excel or PDF (PDF requires manual data entry — biggest pain point)
3. Copy all bidder prices into a **consolidated comparison spreadsheet**
4. Check for: unquoted items, arithmetic errors, description changes
5. Identify **unbalanced bidding** (front-loading costs on early milestones)
6. Prepare negotiation notes per bidder (outliers, over/underpricing)
7. Multiple negotiation rounds (3-4 rounds), re-extract and compare each time
8. Final evaluation includes financial standing, capacity, running projects
9. ADDC provides standardized BOQ template — bidders fill in their prices

## Solution Pipeline
1. **Extract** — OCR/parse bid documents (PDF/Excel) into structured data
2. **Normalize** — Map to common BOQ schema, validate items match ADDC template
3. **Compare** — Consolidated view of all bidders per line item across rounds
4. **Analyze** — Flag unquoted items, math errors, unbalanced bidding, outliers
5. **Report** — Generate comparison summary + negotiation preparation notes

## Sample Data (Tender D-111808)
Construction of 3 primary substations in Eastern Region (SHBPRY, DRPRY, SMHPRY).

### Bidders
| Bidder | Rounds | Has Excel | Has PDF |
|--------|--------|-----------|---------|
| AGPOWER | Original, Round 1, Round 2 | Yes (BOQ per lot + summary) | Yes (BOQ per lot + summary) |
| AL Geemi | Original, Round 1, Round 2, Round 3 | Yes (BOQ per lot + summary) | Yes (commercial submission, 121 pages) |

### BOQ Structure (per lot file)
- **Sheets**: Final Summary, Items 1-3 (Construction), Item 4 (Load Diversion), Items 5-8 (Dismantling), Item 9 (Spare Parts)
- **Columns**: Item, Description, Unit, Qty, CIF Unit Rate, CIF Total, Erection Unit Rate, Erection Total, Total A+B
- **~218 rows** per lot for construction works, ~73 for load diversion, ~158 for spare parts
- Lots can be awarded separately or together (affects pricing strategy)

### Price Summary (Total Contract, all lots combined)
| Bidder | Original | Round 1 | Round 2 | Round 3 |
|--------|----------|---------|---------|---------|
| AL Geemi | 179.4M | 171.7M | 170.4M | 167.0M (incl 3.39M discount) |
| AGPOWER | ~64.2M* | ~47.4M* | ~46.9M* | — |

*AGPOWER totals approximate — summed from lot-level data, no combined total in their files.

Note: AGPOWER's pricing is dramatically lower. Their CIF/Erection split is more balanced
(26M/7.5M) vs AL Geemi's front-loaded supply costs (30M/1.5M).

## Technical Findings
- **Excel extraction**: openpyxl works perfectly — structured data, clean columns
- **PDF extraction (digital)**: PyMuPDF `find_tables()` achieves ~95% accuracy on these BOQs
- **OCR requirement**: needed for scanned/stamped PDFs (real-world bidder submissions)
- **OCR options evaluated**: Azure Document Intelligence or Google Document AI recommended for production; docTR/Surya for POC
- BOQ template is ADDC-standardized — same item numbers across all bidders

## Project Structure
```
bid_analyzer_demo/
  CLAUDE.md              # this file
  pyproject.toml         # uv project config (Python 3.11.11)
  main.py
  data/
    power/
      AGPOWER/           # Bidder 1
        original/excel/  # 4 xlsx (3 lots + summary)
        original/pdf/    # 4 pdf
        round1/excel/
        round1/pdf/
        round2/excel/
        round2/pdf/
        transcript.md    # (empty — was placeholder)
      AL Geemi/          # Bidder 2
        original/excel/  # 4 xlsx
        original/pdf/    # 1 commercial submission PDF (121 pages)
        round1/excel/ + pdf/
        round2/excel/ + pdf/
        round3/excel/ + pdf/
  project_details/
    bid_use_case.png     # Use case charter slide (business case numbers)
    power_transcript.md  # Call transcript with Mohammed Al Katheri
  archieved/             # Old files from earlier exploration
```

## Environment
- **Python**: 3.11.11 via uv
- **Installed packages**: openpyxl, pymupdf, pandas
- **Activate**: `source .venv/bin/activate`

## Next Steps
- [ ] Build POC extraction pipeline (PDF -> structured data)
- [ ] Implement OCR path for scanned PDFs
- [ ] Create consolidated comparison spreadsheet generator
- [ ] Add unquoted item detection + arithmetic error checking
- [ ] Explore water/other bid types (different BOQ structures expected)
- [ ] Build demo UI or notebook for stakeholder review
