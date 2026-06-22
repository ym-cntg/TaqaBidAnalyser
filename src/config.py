from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnMapping:
    item_no: str = "A"
    description: str = "B"
    unit: str = "C"
    qty: str = "D"
    cif_unit_rate: str = "E"
    cif_total: str = "F"
    erection_unit_rate: str = "G"
    erection_total: str = "H"
    total_price: str = "I"


@dataclass(frozen=True)
class BOQConfig:
    name: str
    header_row: int  # row with "Item", "Description", etc.
    data_start_row: int  # first row of actual line items
    columns: ColumnMapping = field(default_factory=ColumnMapping)
    sections: tuple[str, ...] = ()
    lot_names: dict[str, str] = field(default_factory=dict)  # lot_id -> display name
    # Summary file config
    summary_header_row: int = 4
    summary_data_start_row: int = 6
    # Lot columns in summary file (lot_id -> (cif_col, erection_col, total_col))
    summary_lot_columns: dict[str, tuple[str, str, str]] = field(default_factory=dict)


# ADDC Power Tender D-111808
POWER_D111808 = BOQConfig(
    name="D-111808 Power Substations",
    header_row=5,
    data_start_row=9,
    columns=ColumnMapping(),
    sections=(
        "Items 1,2,3-Construction Works",
        "Items 4-Load Diversion Works",
        "Items 5-8 Dismantl & Modif work",
        "Items 9- Spare Parts (Optional)",
    ),
    lot_names={
        "Lot 1": "SHBPRY",
        "Lot 2": "DRPRY",
        "Lot 3": "SMHPRY",
    },
    summary_header_row=4,
    summary_data_start_row=6,
    summary_lot_columns={
        "Lot 1": ("C", "D", "E"),
        "Lot 2": ("F", "G", "H"),
        "Lot 3": ("I", "J", "K"),
    },
)

# File naming patterns to identify lot from filename
LOT_PATTERNS = {
    "Lot 1": ["lot 1", "lot1", "shbpry", "lot-1"],
    "Lot 2": ["lot 2", "lot2", "drpry", "lot-2"],
    "Lot 3": ["lot 3", "lot3", "smhpry", "lot-3"],
}

SUMMARY_PATTERNS = ["summary", "summaryoflot"]

# Round name normalization
ROUND_ALIASES = {
    "original": "original",
    "round 1": "round1",
    "round1": "round1",
    "round 2": "round2",
    "round2": "round2",
    "round 3": "round3",
    "round3": "round3",
    "round 4": "round4",
    "round4": "round4",
}
