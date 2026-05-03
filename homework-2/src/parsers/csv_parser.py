import csv
import io
from collections.abc import Iterable
from typing import Any

from src.parsers.base import ParserError


def _split_tags(value: str) -> list[str]:
    if not value:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


class CsvTicketParser:
    def parse(self, content: bytes) -> Iterable[dict[str, Any]]:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParserError(f"CSV is not valid UTF-8: {exc}") from exc

        reader = csv.DictReader(io.StringIO(decoded))
        if reader.fieldnames is None:
            raise ParserError("CSV is empty or has no header row")

        records: list[dict[str, Any]] = []
        for row in reader:
            record: dict[str, Any] = {
                "customer_id": row.get("customer_id", ""),
                "customer_email": row.get("customer_email", ""),
                "customer_name": row.get("customer_name", ""),
                "subject": row.get("subject", ""),
                "description": row.get("description", ""),
            }
            for optional in ("category", "priority", "status", "assigned_to"):
                if row.get(optional):
                    record[optional] = row[optional]

            if row.get("tags"):
                record["tags"] = _split_tags(row["tags"])

            metadata: dict[str, Any] = {}
            for meta_field in ("source", "browser", "device_type"):
                if row.get(meta_field):
                    metadata[meta_field] = row[meta_field]
            if metadata:
                record["metadata"] = metadata

            records.append(record)
        return records
