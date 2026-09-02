from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class OrderRow:
    room: str
    item_type: str
    size_area: str = ""
    description: str = ""
    measured_qty: float | None = None
    order_qty: float | str | None = None
    unit: str = ""
    comments: str = ""
    pattern: str = ""
    source_text: str = ""
    waste_percent: float | None = None
    order_components: tuple[float, ...] = ()
    order_formula_override: str = ""
    related_type: str = ""
    room_context: str = ""


def clean_text(value: str) -> str:
    value = value.replace("�", '"').replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", value).strip()
