from __future__ import annotations

import re
from collections import OrderedDict

from cosmo_tiling.parsers.common import OrderRow, clean_text

def parse_saussy_metadata(lines: list[str]) -> OrderedDict[str, str]:
    header = " ".join(lines[:40])
    metadata: OrderedDict[str, str] = OrderedDict()
    metadata["Document"] = "Saussy Burbank Design Selection Sheet"

    buyer_match = re.search(
        r"Saussy Burbank Buyer:\s*(.*?)\s+Community:\s*(.*?)\s+Design Selection Sheet",
        header,
        re.IGNORECASE,
    )
    address_match = re.search(
        r"Design Selection Sheet Address:\s*(.*?)\s+Specifications:\s*(.*?)\s+Lot Number:",
        header,
        re.IGNORECASE,
    )
    lot_match = re.search(
        r"Lot Number:\s*(.*?)\s+Revision Date:\s*(.*?)\s+Plan Name:",
        header,
        re.IGNORECASE,
    )
    plan_match = re.search(
        r"Plan Name:\s*(.*?)\s+Revisions per CO:\s*(.*?)\s+CO Source",
        header,
        re.IGNORECASE,
    )

    buyer = clean_text(buyer_match.group(1)) if buyer_match else ""
    community = clean_text(buyer_match.group(2)) if buyer_match else ""
    address = clean_text(address_match.group(1)) if address_match else ""
    lot = clean_text(lot_match.group(1)) if lot_match else ""
    revision_date = clean_text(lot_match.group(2)) if lot_match else ""
    plan = clean_text(plan_match.group(1)) if plan_match else ""
    revisions = clean_text(plan_match.group(2)) if plan_match else ""

    if revision_date:
        metadata["Revision Date"] = revision_date
    metadata["Builder"] = "Saussy Burbank"
    if lot:
        metadata["Project"] = f"{community} Lot {lot}".strip()
    else:
        metadata["Project"] = buyer or plan
    if buyer:
        metadata["Customer"] = buyer
    if address:
        metadata["Job Address"] = address
    if plan:
        metadata["Plan"] = plan
    if community:
        metadata["Community"] = community
    if revisions:
        metadata["Revisions"] = revisions
    return metadata

def build_saussy_rows(lines: list[str], rules: dict) -> tuple[list[OrderRow], dict[str, str]]:
    if not any(line == "Tile" for line in lines):
        raise ValueError("The Saussy PDF does not contain a Tile section")
    configured_rows = rules.get("rows")
    if not configured_rows:
        return parse_saussy_tile_rows(lines, rules), rules.get("display_names", {})

    rows: list[OrderRow] = []
    for configured in configured_rows:
        measured = configured.get("measured_qty")
        waste = configured.get("waste_percent")
        components = configured.get("order_components")
        if components is None and waste is not None and measured is not None:
            components = [measured]
        rows.append(OrderRow(
            room=configured["room"],
            item_type=configured["type"],
            size_area=configured.get("size", ""),
            description=configured.get("description", ""),
            measured_qty=measured,
            order_qty=configured.get("order_qty"),
            unit=configured.get("unit", ""),
            comments=configured.get("comments", ""),
            pattern=configured.get("pattern", ""),
            source_text=configured.get(
                "source_text", "Saussy Design Selection Sheet / template order rule"
            ),
            waste_percent=waste,
            order_components=tuple(components or ()),
            order_formula_override=configured.get("order_formula", ""),
        ))
    return rows, rules.get("display_names", {})


SAUSSY_SIZE_RE = re.compile(
    r"^(?P<description>.+?)\s+"
    r"(?P<size>\d+(?:\.\d+)?(?:[\"']?)x\d+(?:\.\d+)?(?:[\"']?)|\d+(?:\.\d+)?[\"']|mosaic)\s+"
    r"(?P<level>\d+)\s+(?P<details>.+)$",
    re.IGNORECASE,
)
SAUSSY_GROUT_RE = re.compile(r"\s+#(?P<number>\d+)\s+(?P<color>.*?)(?:\s*[xX]?\s*Tile to ceiling.*)?$")


def saussy_tile_section(lines: list[str]) -> list[str]:
    """Return only the selection-table rows beneath the Saussy Tile heading."""
    start = lines.index("Tile") + 1
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith("Location Qty.") or re.match(r"^Page \d+/\d+$", line):
            break
        section.append(line)
    return section


def parse_saussy_selection(
    room: str, item_type_value: str, value: str, source_text: str, rules: dict
) -> OrderRow | None:
    match = SAUSSY_SIZE_RE.match(value.strip())
    if not match:
        return None

    details = match.group("details").strip()
    grout_match = SAUSSY_GROUT_RE.search(details)
    grout = ""
    if grout_match:
        grout = f"#{grout_match.group('number')} {grout_match.group('color').strip()}"
        orientation = details[: grout_match.start()].strip()
    else:
        orientation = details

    waste = rules.get("waste_percent_by_type", {}).get(item_type_value)
    comments = f"Grout: {grout}" if grout else ""
    return OrderRow(
        room=room,
        item_type=item_type_value,
        size_area=match.group("size"),
        description=match.group("description").strip(),
        measured_qty=None,
        order_qty=None,
        unit="SF",
        comments=comments,
        pattern=orientation,
        source_text=source_text,
        waste_percent=waste,
        related_type=item_type_value,
    )


def parse_saussy_tile_rows(lines: list[str], rules: dict) -> list[OrderRow]:
    """Parse a Saussy tile table without requiring a job-specific profile.

    Saussy's table visually merges each bathroom name across several rows. PDF
    extraction places that name on the shower-floor/niche row, so bathroom
    selections are buffered until their room label appears.
    """
    rows: list[OrderRow] = []
    pending_bathroom: list[tuple[str, str, str]] = []

    def flush_bathroom(room: str) -> None:
        for item_type_value, value, source in pending_bathroom:
            parsed = parse_saussy_selection(room, item_type_value, value, source, rules)
            if parsed:
                rows.append(parsed)
        pending_bathroom.clear()

    direct_prefixes = (
        ("Kitchen Tile Backsplash ", "Kitchen", "KBS Tile"),
        ("Butlers Pantry BS ", "Butlers Pantry", "KBS Tile"),
        ("Laundry Floor ", "Laundry", "Floor Tile"),
        ("Laundry Tile Backsplash ", "Laundry", "Backsplash"),
    )
    bathroom_prefixes = (
        ("Bathroom Floor ", "Floor Tile"),
        ("Tub Surround ", "Shower wall"),
        ("Shower Surround ", "Shower wall"),
    )

    for line in saussy_tile_section(lines):
        if line.startswith(("Location Collection ", "Extension ", "Other/Details")):
            continue

        direct = next((entry for entry in direct_prefixes if line.startswith(entry[0])), None)
        if direct:
            prefix, room, item_type_value = direct
            parsed = parse_saussy_selection(room, item_type_value, line[len(prefix):], line, rules)
            if parsed:
                rows.append(parsed)
            continue

        bathroom = next((entry for entry in bathroom_prefixes if line.startswith(entry[0])), None)
        if bathroom:
            prefix, item_type_value = bathroom
            value = line[len(prefix):].strip()
            if value:
                pending_bathroom.append((item_type_value, value, line))
            continue

        room_match = re.match(
            r"^(Owner's|Bath\s+\d+(?:\s+\([^)]*\))?)\s+(?:Tile\s+)?Shower Floor(?:\s+(.*))?$",
            line,
            re.IGNORECASE,
        )
        if room_match:
            room_label = room_match.group(1)
            room = "Owner's Bath" if room_label.casefold() == "owner's" else room_label
            flush_bathroom(room)
            value = (room_match.group(2) or "").strip()
            if value:
                parsed = parse_saussy_selection(room, "Shower Floor", value, line, rules)
                if parsed:
                    rows.append(parsed)
            continue

        drop_zone = re.match(r"^Floor\s+(.+)$", line)
        if drop_zone:
            parsed = parse_saussy_selection("Drop Zone", "Tile", drop_zone.group(1), line, rules)
            if parsed:
                rows.append(parsed)

    if pending_bathroom:
        flush_bathroom("Bathroom")
    if not rows:
        raise ValueError("No populated tile selections were found in the Saussy Tile section")
    return rows
