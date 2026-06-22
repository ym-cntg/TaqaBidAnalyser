from pathlib import Path

from src.config import POWER_D111808
from src.orchestrator import run_analysis


def main():
    project_root = Path(__file__).parent
    data_path = project_root / "data" / "power"
    output_dir = project_root / "output"

    run_analysis(
        tender_id="D-111808",
        tender_name="Construction of 3 Primary Substations in Eastern Region",
        data_path=data_path,
        config=POWER_D111808,
        output_dir=output_dir,
        target_round="original",
    )


if __name__ == "__main__":
    main()
