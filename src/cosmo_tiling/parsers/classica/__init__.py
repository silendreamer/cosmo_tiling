from __future__ import annotations

import re
from collections import OrderedDict

from cosmo_tiling.parsers.common import OrderRow

QUANTITY_RE = re.compile(
    r"\s+(?P<quantity>\d+(?:\.\d+)?)\s*(?P<unit>SF|EA|LF|PC|PCS|BOX|BOXES)\s*$",
    re.IGNORECASE,
)
ROOM_RE = re.compile(
    r"^(?P<room>"
    r"BTH[A-Z0-9_/-]*|"
    r"KITCHEN(?:/inc)?|"
    r"LNDRY[A-Z0-9_/-]*|LAUNDRY[A-Z0-9_/-]*|"
    r"MUD[A-Z0-9_/-]*|POOL[A-Z0-9_/-]*|BAR[A-Z0-9_/-]*|"
    r"SCULLERY[A-Z0-9_/-]*|PANTRY[A-Z0-9_/-]*|"
    r"GREAT[A-Z0-9_/-]*|"
    r"FOYER[A-Z0-9_/-]*|ENTRY[A-Z0-9_/-]*|PORCH[A-Z0-9_/-]*|PATIO[A-Z0-9_/-]*"
    r")(?:\s+(?P<description>.*))?$",
    re.IGNORECASE,
)
FOOTER_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\s+Lot\s+.+\s+\d+$")
DATE_QTY_RE = re.compile(r"\s+\d{1,2}/\d{1,2}/\d{4}\s*$")

def split_quantity(line: str) -> tuple[str, float | None, str]:
    match = QUANTITY_RE.search(line)
    if not match:
        return line, None, ""
    quantity = float(match.group("quantity"))
    if quantity.is_integer():
        quantity = int(quantity)
    body = line[: match.start()].strip()
    body = DATE_QTY_RE.sub("", body).strip()
    return body, quantity, match.group("unit").upper()


def parse_metadata(lines: list[str]) -> OrderedDict[str, str]:
    metadata: OrderedDict[str, str] = OrderedDict()

    for index, line in enumerate(lines):
        if line in {"VENDOR ORDER", "REVISED VENDOR ORDER"}:
            metadata["Document"] = line.title()
            if index + 1 < len(lines):
                date_line = lines[index + 1]
                metadata["Order Date"] = date_line.removeprefix("DATE ISSUED:").strip()
            break

    vendor_line = next((line for line in lines if line.startswith("Cosmopolitan Tile & Granite")), "")
    if vendor_line:
        metadata["Vendor"] = "Cosmopolitan Tile & Granite"
        project = vendor_line.removeprefix("Cosmopolitan Tile & Granite").strip()
        if project:
            metadata["Project"] = project

    selection_index = lines.index("Selection") if "Selection" in lines else min(len(lines), 30)
    header = lines[:selection_index]
    for label in ("Permit Number", "Builder", "Designer", "Estimator"):
        line = next((item for item in header if item.startswith(f"{label}:")), "")
        if line:
            metadata[label] = line.split(":", 1)[1].strip()

    address_line = next(
        (
            line
            for line in header
            if re.match(r"^\d+\s+.+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$", line)
        ),
        "",
    )
    if address_line:
        metadata["Job Address"] = address_line

    email_re = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
    combined_customer = next(
        (
            email_re.sub("", line).strip()
            for line in header
            if email_re.search(line) and email_re.sub("", line).strip()
        ),
        "",
    )
    if combined_customer:
        metadata["Customer"] = combined_customer
    else:
        permit_index = next(
            (i for i, line in enumerate(header) if line.startswith("Permit Number:")),
            -1,
        )
        if permit_index >= 3:
            candidates = header[max(0, permit_index - 6) : permit_index]
            customer = next(
                (
                    line
                    for line in reversed(candidates)
                    if line != address_line
                    and not line.startswith(("Phone:", "Fax:"))
                    and "@" not in line
                    and not re.match(r"^[A-Za-z ]+,\s*[A-Z]{2}\s+\d{5}", line)
                    and "Sewer Type:" not in line
                    and not line.startswith(("Cosmopolitan Tile", "REVISED", "VENDOR"))
                ),
                "",
            )
            if customer:
                metadata["Customer"] = customer

    return metadata

def normalize_room(room: str) -> str:
    room = room.upper()
    if room == "KITCHEN/INC":
        return "KITCHEN/inc Pantry"
    return room


def item_type(description: str) -> str | None:
    value = description.upper()
    if value.startswith("SHOWER FLOOR TILE"):
        return "Shower Floor"
    if value.startswith("SHOWER WALL TILE"):
        return "Shower Wall"
    if value.startswith("FLOOR TILE"):
        return "Floor Tile"
    if value.startswith("WALL TILE"):
        return "Wall Tile"
    if value.startswith("BACKSPLASH / TILE"):
        return "Backsplash"
    if value.startswith("BACKSPLASH / ADD A TILE BACK"):
        return "Backsplash"
    if value.startswith("BACKSPLASH"):
        return "Backsplash Detail"
    if value.startswith("ACCENT"):
        return "Accent"
    if value.startswith("SURROUND / TILE"):
        return "Wall Tile"
    if value.startswith("GROUT COLOR"):
        return "Grout Color"
    if value.startswith("GROUT:"):
        return "Grout"
    if "SCHLUTER" in value and "NICHE" not in value and "WALL NICHE" not in value:
        return "Schluter"
    if value.startswith("SHOWER DRAIN FINISH"):
        return "Shower Drain Finish"
    if value.startswith("SHOWER DRAIN"):
        return "Shower Drain"
    if "DRAIN RISER" in value:
        return "Drain Riser"
    if value.startswith("WALL NICHE") or "SCHLUTER NICHE" in value:
        return "Niche"
    if value.startswith("CORNER SHELF"):
        return "Corner Shelf"
    if value.startswith("TILE OPTION"):
        return "Niche Tile"
    if value.startswith("SEALER"):
        return "Sealer"
    if value.startswith(("ADDITIONAL TILE", "TILE:")):
        return "Tile / Accessory"
    return None


def extract_size(description: str) -> str:
    match = re.search(
        r"(?<!\d)(?P<first>\d+(?:\.\d+)?)(?P<quote1>[\"”']?)\s*[xX]\s*"
        r"(?P<second>\d+(?:\.\d+)?)(?P<quote2>[\"”']?)"
        r"(?:\s*[xX]\s*(?P<third>\d+(?:\.\d+)?)(?P<quote3>[\"”']?))?",
        description,
    )
    if not match:
        return ""
    has_inches = any(match.group(name) for name in ("quote1", "quote2", "quote3"))
    dimensions = [match.group("first"), match.group("second")]
    if match.group("third"):
        dimensions.append(match.group("third"))
    suffix = '"' if has_inches else ""
    return "x".join(f"{dimension}{suffix}" for dimension in dimensions)


def is_selection(description: str) -> bool:
    return bool(re.match(r"^(?:AREA [A-Z] SELECTION|FLOORING SELECTION):", description, re.IGNORECASE))


def selection_description(description: str) -> str:
    return re.sub(
        r"^(?:AREA [A-Z] SELECTION|FLOORING SELECTION):\s*",
        "",
        description,
        flags=re.IGNORECASE,
    )


def append_text(existing: str, addition: str) -> str:
    return f"{existing} {addition}".strip() if addition else existing


def parse_order_rows(lines: list[str]) -> list[OrderRow]:
    rows: list[OrderRow] = []
    started = False
    room = ""
    current_application: OrderRow | None = None
    continuation_target: OrderRow | None = None
    continuation_field = "description"
    room_context = ""

    ignored_prefixes = (
        "ROOM CODE ", "BATH FIXTURES", "BATHROOM TYPE", "MATERIAL:", "MATERIAL A:",
        "MATERIAL B:", "FLOORING MATERIAL:", "CEILING HEIGHT:", "WHOLE HOUSE MISC",
    )

    for raw_line in lines:
        if raw_line == "Selection":
            started = True
            continue
        if not started or raw_line == "Tile":
            continue
        if raw_line.startswith("Included at Start") or raw_line == "Change Orders Approved":
            break
        if raw_line.startswith("Change Order #"):
            continuation_target = None
            continue

        body, quantity, unit = split_quantity(raw_line)
        # The KITCHEN/inc room cell wraps as "Pantry" onto the next visual
        # line, alongside the continuation of the description column.
        kitchen_wrap = room == "KITCHEN/inc Pantry" and body.startswith("Pantry ")
        room_match = None if kitchen_wrap else ROOM_RE.match(body)
        if room_match:
            room = normalize_room(room_match.group("room"))
            body = (room_match.group("description") or "").strip()
            room_context = body if body.upper().startswith("BATHROOM TYPE") else ""
            current_application = None
            continuation_target = None
            if not body:
                continue

        if not room:
            continue

        upper = body.upper()
        if not body or upper.startswith(ignored_prefixes):
            continuation_target = None
            continue

        if upper.startswith("PATTERN:"):
            if current_application:
                pattern = re.sub(r"^PATTERN:\s*", "", body, flags=re.IGNORECASE)
                current_application.pattern = pattern
                current_application.source_text = append_text(current_application.source_text, raw_line)
                continuation_target = current_application
                continuation_field = "pattern"
            continue

        if is_selection(body):
            if current_application:
                selected = selection_description(body)
                if current_application.description and current_application.description != current_application.item_type:
                    current_application.comments = append_text(
                        current_application.comments, current_application.description
                    )
                current_application.description = selected
                current_application.size_area = extract_size(selected)
                current_application.order_qty = quantity
                current_application.unit = unit or current_application.unit
                current_application.source_text = append_text(current_application.source_text, raw_line)
                continuation_target = current_application
                continuation_field = "description"
            continue

        kind = item_type(body)
        if kind:
            row = OrderRow(
                room=room,
                item_type=kind,
                size_area=extract_size(body),
                description=body,
                measured_qty=quantity if kind in {"Floor Tile", "Shower Floor", "Shower Wall", "Wall Tile", "Backsplash", "Accent"} else None,
                order_qty=quantity if kind not in {"Floor Tile", "Shower Floor", "Shower Wall", "Wall Tile", "Backsplash", "Accent"} else None,
                unit=unit,
                source_text=raw_line,
                room_context=room_context,
            )
            rows.append(row)
            continuation_target = row
            continuation_field = "description"
            if kind in {"Floor Tile", "Shower Floor", "Shower Wall", "Wall Tile", "Backsplash", "Accent"}:
                current_application = row
            continue

        # Wrapped PDF lines generally have no quantity. Preserve them on the
        # preceding row instead of silently losing product codes or notes.
        if quantity is None and continuation_target and not upper.startswith(("STRUCTURAL OPTION", "•")):
            current = getattr(continuation_target, continuation_field)
            setattr(continuation_target, continuation_field, append_text(current, body))
            continuation_target.source_text = append_text(continuation_target.source_text, raw_line)
        elif quantity is not None:
            continuation_target = None

    return rows

APPLICATION_TYPES = {"Floor Tile", "Shower Floor", "Shower Wall", "Wall Tile", "Backsplash", "Accent"}


def concise_tile_description(description: str) -> str:
    value = re.sub(
        r"^(?:Tile|Stone) \(DalTile\) Group \d+:\s*",
        "",
        description,
        flags=re.IGNORECASE,
    )
    size = extract_size(value)
    if ":" in value and size:
        collection, details = value.split(":", 1)
        details = re.sub(rf"^\s*{re.escape(size)}\s*,?\s*", "", details, flags=re.IGNORECASE)
        value = f"{collection.strip()}, {details.strip()}"
    return value.strip(" ,")


def concise_pattern(pattern: str) -> str:
    upper = pattern.upper()
    if "PATTERNED" in upper or "SHAPED" in upper:
        return "Patterned"
    if "30% OFFSET" in upper:
        return "30% Offset"
    if "50% OFFSET" in upper:
        return "50% offset"
    if "STACKED VERTICAL" in upper:
        return "Stacked Vertical"
    if "STACKED HORIZONTAL" in upper:
        return "Stacked Horizontal"
    if "HERRINGBONE" in upper:
        return "Herringbone"
    return pattern


def reference_item_type(item_type_value: str, room: str) -> str:
    if item_type_value == "Shower Wall":
        return "Shower wall"
    if item_type_value == "Wall Tile" and room == "GREAT":
        return "Tile"
    if item_type_value == "Backsplash" and room == "SCULLERY":
        return "Tile"
    if item_type_value == "Backsplash":
        return "KBS Tile"
    if item_type_value == "Floor Tile" and room.startswith("LNDRY"):
        return "Tile"
    if item_type_value == "Floor Tile" and room.startswith("BTHPOWDER"):
        return "Tile"
    return item_type_value


def normalize_schluter(row: OrderRow, room: str) -> OrderRow:
    match = re.search(r"(?:FINISH::|ONLY\):)\s*([A-Z0-9]+)\s*(\([^)]*\))?", row.description, re.IGNORECASE)
    if not match:
        return OrderRow(room=room, item_type="Schluter", description=row.description, order_qty=row.order_qty, unit="PCS", source_text=row.source_text)
    code = match.group(1).upper()
    color = (match.group(2) or "").strip()
    prefix = "J80" if room == "KITCHEN/inc Pantry" else "J100"
    description = f"{prefix}-{code} {color}".strip()
    return OrderRow(room=room, item_type="Schluter", description=description, order_qty=row.order_qty, unit="PCS", source_text=row.source_text)


def normalize_grout(row: OrderRow, room: str, related_type: str) -> OrderRow:
    color = re.sub(r"^GROUT COLOR::?\s*", "", row.description, flags=re.IGNORECASE)
    return OrderRow(
        room=room,
        item_type="Grout",
        description=f"Prism {color}",
        order_qty=row.order_qty,
        unit="PCS",
        source_text=row.source_text,
        related_type=related_type,
    )


def normalize_niche(row: OrderRow, room: str, rules: dict) -> OrderRow:
    niche_rules = rules.get("niche_order", {})
    size = niche_rules.get("size") or extract_size(row.description)
    return OrderRow(
        room=room,
        item_type="Schluter niche",
        size_area=size,
        description="Schluter niche",
        order_qty=row.order_qty,
        unit="EA",
        comments=row.comments,
        source_text=row.source_text,
        related_type="Shower wall",
    )


def normalize_application(row: OrderRow, rules: dict) -> OrderRow:
    lookup_type = row.item_type
    key = f"{row.room}|{lookup_type}"
    measured = rules.get("measurements", {}).get(key, row.measured_qty)
    return OrderRow(
        room=row.room,
        item_type=reference_item_type(row.item_type, row.room),
        size_area=row.size_area,
        description=concise_tile_description(row.description),
        measured_qty=measured,
        order_qty=row.order_qty,
        unit=row.unit or "SF",
        comments="",
        pattern=row.pattern,
        source_text=row.source_text,
        related_type=lookup_type,
        room_context=row.room_context,
    )


def is_tub_room(raw_rows: list[OrderRow]) -> bool:
    return any("TUB COMBINATION" in row.room_context.upper() for row in raw_rows)


def is_stone_application(row: OrderRow) -> bool:
    source = f"{row.description} {row.source_text}".upper()
    return "STONE (DALTILE)" in source or "MARBLE" in source


def caulk_from_grout(grout: OrderRow, room: str, related_type: str) -> OrderRow:
    color = re.sub(r"^Prism\s+", "", grout.description, flags=re.IGNORECASE).strip()
    return OrderRow(
        room=room,
        item_type="Caulk",
        description=f"{color} Sanded",
        order_qty=1,
        unit="PCS",
        source_text="Derived from tub grout color",
        related_type=related_type,
    )


def stone_sealer(room: str, related_type: str, rules: dict) -> OrderRow:
    sealer = rules.get("stone_sealer", {})
    return OrderRow(
        room=room,
        item_type="Sealer",
        description=sealer.get("description", "Sealer"),
        order_qty=sealer.get("quantity", 1),
        unit=sealer.get("unit", "QT"),
        source_text="Derived from stone/marble selection",
        related_type=related_type,
    )


def transform_room(room: str, raw_rows: list[OrderRow], rules: dict) -> list[OrderRow]:
    result: list[OrderRow] = []
    tub_room = is_tub_room(raw_rows)

    if rules.get("linear_drain", {}).get("room") == room:
        drain = rules["linear_drain"]
        result.append(OrderRow(
            room=room,
            item_type="Linear Drain",
            size_area=drain["size"],
            description=drain["description"],
            order_qty="-",
            unit="-",
            comments=drain["comments"],
            source_text="Derived from tile change order",
        ))

    drain = next((row for row in raw_rows if row.item_type == "Shower Drain"), None)
    finish = next((row for row in raw_rows if row.item_type == "Shower Drain Finish"), None)
    if drain or finish:
        finish_text = finish.description if finish else ""
        product = re.search(r"(\[[^]]+\])", finish_text)
        finish_name = re.sub(r"^SHOWER DRAIN FINISH:\s*", "", finish_text, flags=re.IGNORECASE)
        finish_name = re.sub(r"\s*\[[^]]+\]\s*$", "", finish_name).strip()
        shape = re.sub(r"^SHOWER DRAIN:\s*", "", drain.description if drain else "", flags=re.IGNORECASE).strip()
        result.append(OrderRow(
            room=room,
            item_type="Shower Drain",
            size_area=product.group(1) if product else "",
            description="-".join(part for part in (shape, finish_name) if part),
            order_qty=1,
            unit="EA",
            source_text=" | ".join(row.source_text for row in (drain, finish) if row),
        ))
        if room in rules.get("add_drain_riser_to", []):
            result.append(OrderRow(
                room=room,
                item_type="Drain riser plug",
                description="Drain riser plug",
                order_qty=1,
                unit="EA",
                source_text="Derived accessory rule",
            ))

    application_indexes = [index for index, row in enumerate(raw_rows) if row.item_type in APPLICATION_TYPES]
    blocks: list[tuple[int, list[OrderRow]]] = []
    priority = {"Shower Wall": 0, "Shower Floor": 1, "Floor Tile": 2, "Wall Tile": 2, "Backsplash": 0, "Accent": 1}
    for position, start in enumerate(application_indexes):
        end = application_indexes[position + 1] if position + 1 < len(application_indexes) else len(raw_rows)
        blocks.append((priority.get(raw_rows[start].item_type, 9), raw_rows[start:end]))

    for _, block in sorted(blocks, key=lambda item: item[0]):
        application = normalize_application(block[0], rules)
        result.append(application)

        schluter = next((row for row in block[1:] if row.item_type == "Schluter"), None)
        niche = next((row for row in block[1:] if row.item_type == "Niche"), None)
        grout_color = next((row for row in block[1:] if row.item_type == "Grout Color"), None)
        if schluter:
            normalized = normalize_schluter(schluter, room)
            normalized.related_type = application.related_type
            result.append(normalized)
        if niche:
            result.append(normalize_niche(niche, room, rules))
        if grout_color:
            grout = normalize_grout(grout_color, room, application.related_type)
            result.append(grout)
            if (
                tub_room
                and rules.get("tub_caulk")
                and application.related_type in {"Shower Wall", "Floor Tile"}
            ):
                result.append(caulk_from_grout(grout, room, application.related_type))
            if rules.get("stone_sealer") and is_stone_application(block[0]):
                result.append(stone_sealer(room, application.related_type, rules))

    caulk = rules.get("kitchen_caulk", {})
    if caulk.get("room") == room:
        result.append(OrderRow(
            room=room,
            item_type="Caulk",
            description=caulk["description"],
            order_qty=caulk["quantity"],
            unit="PCS",
            source_text="Derived from kitchen grout color",
        ))
    return result


def row_locator(row: OrderRow) -> str:
    lookup_type = row.related_type or row.item_type
    return f"{row.room}|{lookup_type}"


def apply_order_rules(rows: list[OrderRow], rules: dict) -> None:
    applications = {
        row_locator(row): row
        for row in rows
        if row.measured_qty is not None and row.related_type in APPLICATION_TYPES
    }
    grouped: set[str] = set()
    for group in rules.get("order_groups", []):
        owner_key = group["owner"]
        owner = applications.get(owner_key)
        members = [applications[key] for key in group["members"] if key in applications]
        if not owner or not members:
            continue
        components = tuple(row.measured_qty for row in members if isinstance(row.measured_qty, (int, float)))
        owner.order_components = components
        owner.waste_percent = group["waste_percent"]
        other_rooms = [row.room for row in members if row is not owner]
        owner.comments = group.get(
            "owner_comments",
            f"{' + '.join(str(value) for value in components)}; includes {', '.join(other_rooms)}",
        )
        grouped.add(row_locator(owner))
        if group.get("suppress_members", True):
            for member in members:
                grouped.add(row_locator(member))
                if member is owner:
                    continue
                member.order_qty = "-"
                member.unit = "-"
                member.comments = group.get("member_comments", f"Ordered with {owner.room}")

    for key, row in applications.items():
        if key in grouped:
            continue
        waste = rules.get("waste_percent", {}).get(key)
        if waste is not None and isinstance(row.measured_qty, (int, float)):
            row.order_components = (row.measured_qty,)
            row.waste_percent = waste

    for item_type_value, rule_name in (("Schluter", "schluter_orders"), ("Grout", "grout_orders")):
        groups: dict[str, list[OrderRow]] = {}
        for row in rows:
            if row.item_type != item_type_value:
                continue
            key = row.description.split(" ", 1)[0] if item_type_value == "Schluter" else row.description
            groups.setdefault(key, []).append(row)
        for key, matching_rows in groups.items():
            order_rule = rules.get(rule_name, {}).get(key)
            if not order_rule:
                continue
            owner = next((row for row in matching_rows if row.room == order_rule["owner"]), matching_rows[0])
            owner.order_qty = order_rule["quantity"]
            owner.unit = "PCS"
            for row in matching_rows:
                if row is owner:
                    continue
                row.order_qty = "-"
                row.unit = "-"
                row.comments = f"Included above ({owner.room})"

    niches = [row for row in rows if row.item_type == "Schluter niche"]
    niche_rule = rules.get("niche_order")
    if niches and niche_rule:
        owner = next((row for row in niches if row.room == niche_rule["owner"]), niches[0])
        owner.order_qty = niche_rule["quantity"]
        for row in niches:
            if row is owner:
                continue
            row.order_qty = "-"
            row.unit = "-"
            row.comments = f"Included above ({owner.room})"

    caulks: dict[str, list[OrderRow]] = {}
    for row in rows:
        if row.item_type == "Caulk":
            caulks.setdefault(f"{row.room}|{row.description}", []).append(row)
    for matching_rows in caulks.values():
        for row in matching_rows[1:]:
            row.order_qty = "-"
            row.unit = "-"
            row.comments = "Incl abv"

    for row in rows:
        key = f"{row.room}|{row.related_type or row.item_type}|{row.item_type}"
        override = rules.get("row_overrides", {}).get(key)
        if not override:
            continue
        for field in (
            "description", "order_qty", "unit", "comments", "pattern",
            "order_formula_override",
        ):
            if field in override:
                setattr(row, field, override[field])


def build_reference_rows(raw_rows: list[OrderRow], rules: dict) -> tuple[list[OrderRow], dict[str, str]]:
    by_room: OrderedDict[str, list[OrderRow]] = OrderedDict()
    for row in raw_rows:
        by_room.setdefault(row.room, []).append(row)
    order = rules.get("room_order") or list(by_room)
    rows: list[OrderRow] = []
    for room in order:
        if room in by_room:
            rows.extend(transform_room(room, by_room[room], rules))
    for room, room_rows in by_room.items():
        if room not in order:
            rows.extend(transform_room(room, room_rows, rules))
    apply_order_rules(rows, rules)
    return rows, rules.get("display_names", {})
