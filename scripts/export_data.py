"""Export CalibraMark data to JSON files for analysis."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from utils.data_storage import DataStorage


TABLES = ["paper_trades", "market_snapshots", "agent_decisions", "calibration_history"]


def export_data(tables: list, output_dir: Path):
    """Export specified tables to JSON files."""
    storage = DataStorage()
    output_dir.mkdir(parents=True, exist_ok=True)

    for table in tables:
        if table not in TABLES:
            print(f"Unknown table: {table}. Available: {TABLES}")
            continue

        filepath = output_dir / f"{table}.json"
        storage.export_to_json(table, filepath)
        print(f"Exported {table} -> {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Export CalibraMark data to JSON")
    parser.add_argument(
        "--tables",
        nargs="+",
        default=TABLES,
        choices=TABLES,
        help="Tables to export",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/exports"),
        help="Output directory",
    )
    args = parser.parse_args()

    export_data(args.tables, args.output_dir)


if __name__ == "__main__":
    main()
