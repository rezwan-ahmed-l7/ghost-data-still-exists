"""Strict, deterministic CSV loading for participant-facing challenge inputs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "deletion_requests.csv": (
        "case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"
    ),
    "sample_deletion_requests.csv": (
        "case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"
    ),
    "sample_output.csv": ("case_id", "deletion_status", "steps_json"),
    "user_identities.csv": ("user_id", "name", "email", "phone", "email_hash", "updated_at"),
    "user_audit_log.csv": ("audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"),
    "system_activity.csv": (
        "activity_id", "event_time", "event_type", "source_system", "target_system", "resource_id",
        "reported_result", "details"
    ),
    "deletion_rules.csv": ("rule_id", "data_category", "condition", "required_action"),
    "evidence_files.csv": ("file_id", "file_path", "origin", "captured_at"),
    "output.csv": ("case_id", "deletion_status", "steps_json"),
}


class DatasetLoadError(ValueError):
    """Raised when a required participant-facing CSV is missing or malformed."""


@dataclass(frozen=True)
class Dataset:
    deletion_requests: List[Dict[str, str]]
    sample_deletion_requests: List[Dict[str, str]]
    sample_output: List[Dict[str, str]]
    user_identities: List[Dict[str, str]]
    user_audit_log: List[Dict[str, str]]
    system_activity: List[Dict[str, str]]
    deletion_rules: List[Dict[str, str]]
    evidence_files: List[Dict[str, str]]
    output_template: List[Dict[str, str]]


def _read_csv(path: Path, expected_headers: tuple[str, ...]) -> List[Dict[str, str]]:
    if not path.is_file():
        raise DatasetLoadError(f"Required CSV not found: {path}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            actual_headers = tuple(reader.fieldnames or ())
            if actual_headers != expected_headers:
                raise DatasetLoadError(
                    f"Invalid headers in {path.name}: expected {expected_headers!r}, got {actual_headers!r}"
                )

            rows: List[Dict[str, str]] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    raise DatasetLoadError(f"Extra CSV field in {path.name}:{line_number}")
                if any(value is None for value in row.values()):
                    raise DatasetLoadError(f"Missing CSV field in {path.name}:{line_number}")
                rows.append({key: value for key, value in row.items()})
            return rows
    except (OSError, csv.Error) as exc:
        raise DatasetLoadError(f"Unable to read {path.name}: {exc}") from exc


def load_dataset(dataset_dir: str | Path) -> Dataset:
    """Load and validate every CSV listed in the repository dataset contract."""
    root = Path(dataset_dir).expanduser().resolve()
    loaded = {
        filename: _read_csv(root / filename, headers)
        for filename, headers in CSV_HEADERS.items()
    }

    request_ids = [row["case_id"] for row in loaded["deletion_requests.csv"]]
    if len(request_ids) != len(set(request_ids)):
        raise DatasetLoadError("deletion_requests.csv contains duplicate case_id values")

    identity_ids = [row["user_id"] for row in loaded["user_identities.csv"]]
    if len(identity_ids) != len(set(identity_ids)):
        raise DatasetLoadError("user_identities.csv contains duplicate user_id values")

    return Dataset(
        deletion_requests=loaded["deletion_requests.csv"],
        sample_deletion_requests=loaded["sample_deletion_requests.csv"],
        sample_output=loaded["sample_output.csv"],
        user_identities=loaded["user_identities.csv"],
        user_audit_log=loaded["user_audit_log.csv"],
        system_activity=loaded["system_activity.csv"],
        deletion_rules=loaded["deletion_rules.csv"],
        evidence_files=loaded["evidence_files.csv"],
        output_template=loaded["output.csv"],
    )
