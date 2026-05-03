import xml.etree.ElementTree as ET  # noqa: S405
from collections.abc import Iterable
from typing import Any

from src.parsers.base import ParserError

_SCALAR_FIELDS = (
    "customer_id",
    "customer_email",
    "customer_name",
    "subject",
    "description",
    "category",
    "priority",
    "status",
    "assigned_to",
)


class XmlTicketParser:
    def parse(self, content: bytes) -> Iterable[dict[str, Any]]:
        try:
            root = ET.fromstring(content)  # noqa: S314
        except ET.ParseError as exc:
            raise ParserError(f"Invalid XML: {exc}") from exc

        ticket_elements = (
            root.findall("ticket") if root.tag == "tickets" else [root]
        )

        result: list[dict[str, Any]] = []
        for el in ticket_elements:
            record: dict[str, Any] = {}
            for field in _SCALAR_FIELDS:
                node = el.find(field)
                if node is not None and node.text is not None:
                    record[field] = node.text.strip()

            tags_el = el.find("tags")
            if tags_el is not None:
                tags = [
                    (t.text or "").strip()
                    for t in tags_el.findall("tag")
                    if t.text and t.text.strip()
                ]
                record["tags"] = tags

            metadata_el = el.find("metadata")
            if metadata_el is not None:
                metadata: dict[str, Any] = {}
                for child in metadata_el:
                    if child.text is not None:
                        metadata[child.tag] = child.text.strip()
                if metadata:
                    record["metadata"] = metadata

            result.append(record)
        return result
