from __future__ import annotations

from dataclasses import dataclass, field

from src.models import TenderData


@dataclass
class RoundMovement:
    bidder: str
    lot: str
    round_totals: dict[str, float] = field(default_factory=dict)

    @property
    def total_change_pct(self) -> float | None:
        """Percentage change from first round to last round."""
        if len(self.round_totals) < 2:
            return None
        rounds = sorted(self.round_totals.keys())
        first = self.round_totals[rounds[0]]
        last = self.round_totals[rounds[-1]]
        if first == 0:
            return None
        return ((last - first) / first) * 100

    @property
    def round_changes(self) -> list[tuple[str, str, float, float]]:
        """List of (from_round, to_round, old_value, new_value) tuples."""
        rounds = sorted(self.round_totals.keys())
        changes = []
        for i in range(len(rounds) - 1):
            changes.append((
                rounds[i],
                rounds[i + 1],
                self.round_totals[rounds[i]],
                self.round_totals[rounds[i + 1]],
            ))
        return changes


@dataclass
class TenderRoundSummary:
    movements: list[RoundMovement] = field(default_factory=list)


def track_rounds(tender: TenderData) -> TenderRoundSummary:
    """Track price movements across negotiation rounds for each bidder/lot."""
    summary = TenderRoundSummary()

    for bidder in tender.bidders:
        for lot in tender.lots:
            round_totals: dict[str, float] = {}

            for round_name in tender.rounds:
                ext = tender.get_extraction(bidder, round_name, lot)
                if ext and ext.total_price is not None:
                    round_totals[round_name] = ext.total_price

            if len(round_totals) >= 1:
                summary.movements.append(RoundMovement(
                    bidder=bidder,
                    lot=lot,
                    round_totals=round_totals,
                ))

    return summary
