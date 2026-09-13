"""Inspect Classica vendor-order columns without project rules.

Usage: uv run python scripts/extract_classica_room.py path/to/vendor-order.pdf ROOM_CODE
Prints all room codes, selected-room JSON, and a five-column table.
"""

import argparse
import json
from pathlib import Path
import re

import pdfplumber

QTY_RE = re.compile(r"\d+(?:[.,]\d+)?\s+(?:SF|EA|LF|PC|PCS|BOX|BOXES|BXS|QT|GAL|ROLLS?)", re.I)


def visual_lines(words):
    """Group words by baseline, allowing small font-height differences."""
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 3:
            lines.append([])
        lines[-1].append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def joined(words):
    return " ".join(word["text"] for word in words)


def extract(path, target=None, apply_revisions=True):
    rooms = []
    records = []
    room = None
    bounds = None
    active = False
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            for line in visual_lines(page.extract_words()):
                text = joined(line)
                if text.startswith("Room Code Type"):
                    anchors = {w["text"]: w["x0"] for w in line}
                    if not {"Type", "Changed", "Qty"} <= anchors.keys():
                        raise ValueError("Incomplete Classica column header")
                    bounds = (anchors["Type"] - 2, anchors["Changed"] - 12,
                              anchors["Qty"] - 12)
                    continue
                if bounds is None:
                    continue
                if text == "Tile":
                    active = True
                    continue
                if not active:
                    continue
                if text.startswith(("Included at Start", "Change Orders", "Change Order #")):
                    return finish_extraction(pdf, rooms, records, target, apply_revisions)
                if re.match(r"\d{1,2}/\d{1,2}/\d{4}\s+Lot\b", text):
                    continue

                description_x, changed_x, qty_x = bounds
                room_words = [w for w in line if w["x0"] < description_x]
                body = [w for w in line if description_x <= w["x0"] < qty_x]
                # Descriptions can extend into an EMPTY Changed column. Only
                # date-shaped words at that column's position are change dates.
                changed = [w for w in body if w["x0"] >= changed_x
                           and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", w["text"])]
                description_words = [w for w in body if w not in changed]
                description = joined(description_words)
                indent = (description_words[0]["x0"] - (description_x + 2)
                          if description_words else None)
                heading = indent is not None and abs(indent) <= 4
                qty = joined([w for w in line if w["x0"] >= qty_x])
                if qty and not QTY_RE.fullmatch(qty):
                    description = " ".join(part for part in (description, qty) if part)
                    qty = ""
                # Wrapped heading text keeps its indentation. Tight line spacing
                # distinguishes it from a new, unquantified heading.
                if (heading and not qty and not changed and records
                        and records[-1]["layout"]["page"] == page_number
                        and line[0]["top"] - records[-1]["layout"].get("last_top", records[-1]["layout"]["top"]) < 11):
                    heading = False
                label = joined(room_words)
                if label:
                    # A wrapped room cell is directly below the previous line,
                    # with no new quantity/date (e.g. KITCHEN/inc + Pantry).
                    if room and not qty and not changed and records and records[-1]["room"] == room:
                        new_room = room + " " + label
                        rooms[rooms.index(room)] = new_room
                        for record in records:
                            if record["room"] == room:
                                record["room"] = new_room
                        room = new_room
                    else:
                        room = label
                        if room not in rooms:
                            rooms.append(room)
                if room is None or not (description or qty or changed):
                    continue
                if not qty and not changed and not heading and records and records[-1]["room"] == room:
                    records[-1]["type_description"] += "\n" + description
                    records[-1]["layout"]["last_top"] = round(line[0]["top"], 2)
                else:
                    records.append({"room": room, "type_description": description,
                                    "selection_changed": joined(changed), "qty": qty,
                                    "layout": {"page": page_number, "top": round(line[0]["top"], 2),
                                               "indent": round(indent, 2) if indent is not None else None,
                                               "is_heading": heading}})
        if bounds is None:
            raise ValueError("Classica Room Code / Type / Changed / Qty header not found")
        return finish_extraction(pdf, rooms, records, target, apply_revisions)


def finish_extraction(pdf, rooms, records, target, apply_revisions=True):
    if __package__:
        from .classica_changes import apply_changes, read_changes
    else:
        from classica_changes import apply_changes, read_changes
    instructions = read_changes("\n".join(page.extract_text() or "" for page in pdf.pages))
    report = apply_changes(records, instructions) if apply_revisions else []
    output = result(rooms, records, target)
    output["change_report"] = report
    return output


def result(rooms, records, target):
    return {"room_codes": rooms, "selected_room": target,
            "rows": [{k: v for k, v in row.items() if k != "room" or target is None}
                     for row in records if target is None or row["room"] == target]}


NUMBER = r'(?:\d+\s+\d+/[1-9]\d*|\d+/[1-9]\d*|\d+(?:\.\d+)?|\d*[\u00bc\u00bd\u00be])'
SIZE_RE = re.compile(
    rf'(?<![\w./]){NUMBER}\s*["\u2033\u201c\u201d\ufffd]?\s*[xX\u00d7]\s*{NUMBER}(?:\s*["\u2033\u201c\u201d\ufffd])?(?![\w./])')
SELECTION_RE = re.compile(r"(?:AREA\s+\w+\s+SELECTION|FLOORING SELECTION)\s*:", re.IGNORECASE)
# Recognition rules only: all product values still come from the PDF.
APPLICATION_ALIASES = {
    "backsplash": "backsplash", "scullery backsplash": "backsplash",
    "floor tile": "floor", "pavers": "pavers",
    "shower floor tile": "shower_floor", "shower floor": "shower_floor",
    "shower wall": "shower_wall", "shower walls": "shower_wall",
    "shower wall tile": "shower_wall", "shower wall tiles": "shower_wall",
    "surround": "surround", "wall tile": "wall",
    "main back wall": "shower_wall_area", "side walls": "shower_wall_area",
    "accent": "accent", "niche tile": "accent",
}
LABEL_ALIASES = {
    "shower drain": "drain_shape", "shower drain finish": "drain_finish",
    "grout color": "grout_color", "grout colour": "grout_color",
    "grout": "context", "pattern": "context", "flooring material": "context",
    "tile option (inside of niche)": "niche_reference",
}


def normalized(text):
    return " ".join(text.split()).casefold()


def application_kind(text, aliases=None):
    return (aliases if aliases is not None else APPLICATION_ALIASES).get(
        normalized(re.split(r"\s*/\s*", text, maxsplit=1)[0]))


def field(text, aliases=None):
    """Normalize labels, preserving the spelling of their values."""
    if SELECTION_RE.match(text):
        return "selection", SELECTION_RE.sub("", text, count=1).strip()
    label, separator, value = text.partition(":")
    key = normalized(label)
    value = value.lstrip(": ")
    if separator:
        kind = (aliases if aliases is not None else LABEL_ALIASES).get(key)
        if kind:
            return kind, value
        if re.fullmatch(r"material(?:\s+\w+)?", key):
            return "context", value
        if re.match(r"schluter\b", key):
            # Remove an optional applicability qualifier, not product colons.
            value = re.sub(r"^\([^)]*\)\s*:\s*", "", value)
            return "schluter", value
    if re.match(r"wall\s+niche\s*/", text, re.IGNORECASE):
        return "niche", text
    if re.match(r"corner\s*shelf\s*/", text, re.IGNORECASE):
        return "corner_shelf", text
    if re.match(r"(?:sealer|grout release)(?:\s*[:/]|$)", text, re.I):
        return "supply", text
    if re.match(r"(?:bath\s+fixtures|bathroom\s+type)\s*/", text, re.IGNORECASE):
        return "context", text
    return "unknown", text


def size_match(text):
    """Reject ambiguous/partial dimensions instead of stripping product text."""
    matches = list(SIZE_RE.finditer(text))
    for match in matches:
        before, after = text[:match.start()], text[match.end():]
        if re.search(r"\d[\d\s/.,]*$", before) or re.match(r"\s*(?:[xX\u00d7]\s*\d|/\s*\d)", after):
            continue
        if len(matches) == 1 or (
                match is matches[0] and len(matches) == 2
                and re.search(r"\bmosaic\b", text[matches[1].end():], re.I)):
            return match
    return None
# Unquantified instructions may share the application's indentation. Recognize
# those explicitly; an unfamiliar heading must still break the previous block.
NOTE_RE = re.compile(
    r"^(?:\*|see\b|install\b|lay\b|align\b|orient\b|alternate\b|change\b|confirm\b|confrim\b|"
    r"stacked\b|vertical\b|running\b|herringbone\b|perpendicular\b|"
    r"tile direction:|selection:|color story:|\d+ rows\b|"
    r"center from\b|main back wall\b|on wall with\b|to ceiling\b|bleached wood\?)",
    re.IGNORECASE,
)
APPLICATION_SUMMARY_RE = re.compile(
    r"^(?P<product>.+?)\s*-\s*GROUT\s*:\s*(?P<grout>.+?)\s+AND\s+SCHLUTER\s*:\s*(?P<schluter>.+?)\s*$",
    re.IGNORECASE,
)


def application_summary(text):
    """Read compact product/grout/trim summaries emitted by some orders."""
    match = APPLICATION_SUMMARY_RE.match(text)
    return match.groupdict() if match else None


def group_applications(raw_rows, application_aliases=None, label_aliases=None):
    """Recognize application headings; isolate unknown headings for review."""
    sections = []
    for row in raw_rows:
        if row.get("excluded_by_change"):
            continue
        text = " ".join(row["type_description"].split())
        item = (text, row["qty"])
        accessory_context = sections and sections[-1]["heading"] and field(
            sections[-1]["heading"][0], label_aliases)[0] in {"niche", "corner_shelf"}
        is_note = not row["qty"] and ((NOTE_RE.match(text)
                                      and not application_kind(text, application_aliases))
                                     or application_summary(text) or (
            accessory_context and not application_kind(text, application_aliases)))
        if row.get("layout", {}).get("is_heading") and not is_note:
            sections.append({"heading": item, "children": []})
        elif sections:
            sections[-1]["children"].append(item)
        else:
            sections.append({"heading": None, "children": [item]})

    blocks, drains, unclassified, niches, shelves = [], [], [], [], []
    for section in sections:
        heading = section["heading"]
        children = section["children"]
        selections = [item for item in children if field(item[0], label_aliases)[0] == "selection"]
        summaries = [(item, application_summary(item[0])) for item in children]
        summaries = [(item, summary) for item, summary in summaries if summary]
        canonical = application_kind(heading[0], application_aliases) if heading else None
        thin_brick = heading and canonical == "surround" and re.search(r"\bthin\s*brick\b", heading[0], re.I)
        if thin_brick:
            details = "; ".join(text for text, _ in children if re.match(r"(?:COLOR|PAINT)\s*:", text, re.I))
            selections = [("AREA A SELECTION: Thin Brick" + ("; " + details if details else ""), heading[1])]
        if canonical and selections:
            # Some PDFs replace product detail with a compact heading and leave
            # only "Tile (...) Group 2" in AREA A SELECTION. Recover only the
            # values stated by that summary; absent size/profile details stay blank.
            if len(summaries) == 1:
                summary = summaries[0][1]
                selections = [
                    ("AREA A SELECTION: " + summary["product"], qty)
                    if re.fullmatch(r"(?:Tile|Stone)\s*\([^)]*\)\s*Group\s+[^:]+",
                                    field(text, label_aliases)[1], re.I)
                    else (text, qty)
                    for text, qty in selections
                ]
            block = {"type": heading[0], "kind": canonical, "selections": selections, "accessories": [],
                     "stone": any(re.search(r"(?:SELECTION|MATERIAL)\s*:\s*Stone\b", text, re.I)
                                  for text, _ in children)}
            blocks.append(block)
        else:
            block = None
        if heading and field(heading[0], label_aliases)[0] == "corner_shelf":
            details = [text for text, _ in children if re.search(r"\bshelf\b", text, re.I)]
            shelves.append(("Corner Shelf / " + " / ".join(details or [heading[0]]), heading[1]))
            unclassified.extend((text, qty) for text, qty in children if text not in details)
            continue
        section_drain = None
        for text, qty in ([heading] if heading else []) + children:
            category, value = field(text, label_aliases)
            summary = application_summary(text)
            if summary and block:
                block["accessories"].extend([
                    ("GROUT COLOR: " + summary["grout"], ""),
                    ("SCHLUTER: " + summary["schluter"], ""),
                ])
                continue
            if category in {"drain_shape", "drain_finish"}:
                key = "shape" if category == "drain_shape" else "finish"
                if section_drain is None or key in section_drain:
                    section_drain = {}
                    drains.append(section_drain)
                section_drain[key] = value
                section_drain["unit"] = qty.split()[-1] if qty else ""
            elif category == "niche":
                reference = next((re.sub(r"^same\s+as\s+", "", value, flags=re.IGNORECASE)
                                  for child, _ in children
                                  for kind, value in [field(child, label_aliases)]
                                  if kind == "niche_reference" and re.match(r"same\s+as\s+", value, re.IGNORECASE)), None)
                niches.append((text, qty, reference))
            elif category in {"schluter", "grout_color"} and block:
                block["accessories"].append((text, qty))
            elif category == "supply":
                if block:
                    block["accessories"].append((text, qty))
                else:
                    blocks.append({"type": text, "selections": [], "accessories": [(text, qty)]})
            elif block and (item_is_heading(text, heading) or category in {"selection", "context"}):
                continue
            elif block and thin_brick and re.match(r"(?:COLOR|PAINT)\s*:", text, re.I):
                continue
            elif category == "niche_reference" or re.match(r"(?:bath fixtures|bathroom type)\s*/", text, re.IGNORECASE):
                continue  # Context remains available in raw JSON.
            else:
                unclassified.append((text, qty))
    walls = [b for b in blocks if b.get("kind") in {"shower_wall", "shower_wall_area"}]
    for text, qty, reference in niches:
        matches = walls
        if len(matches) > 1 and all(match.get("kind") == "shower_wall_area" for match in matches):
            matches = matches[-1:]
        if len(matches) == 1:
            matches[0]["accessories"].append((text, qty))
            interior = [b for b in blocks if reference and application_kind(reference, application_aliases)
                        and b.get("kind") == application_kind(reference, application_aliases)]
            if len(interior) == 1 and interior[0] is not matches[0]:
                matches[0].setdefault("accents", []).extend(interior[0]["selections"])
        else:
            blocks.append({"type": text, "selections": [], "accessories": [(text, qty)]})
    for shelf in shelves:
        if len(walls) == 1:
            walls[0]["accessories"].append(shelf)
        else:
            blocks.append({"type": "Corner Shelf", "selections": [], "accessories": [shelf]})
    return blocks, drains, unclassified


def item_is_heading(text, heading):
    return heading is not None and text == heading[0]


def product_fields(text, label_aliases=None):
    description = field(text, label_aliases)[1]
    description = re.sub(r"^(?:Tile|Stone)\s*\([^)]*\)\s*Group\s+[^:]+:\s*",
                         "", description, flags=re.I)
    size = size_match(description)
    if size:
        description = description[:size.start()] + description[size.end():]
    description = re.sub(r"\s*:\s*", ", ", description)
    description = re.sub(r",\s*,", ",", description).strip(" ,")
    description = re.sub(r"\s+,", ",", description)
    return size.group().strip() if size else "", description


def table_rows(raw_rows, application_aliases=None, label_aliases=None):
    """Render source values plus the approved caulk and drain-riser rules."""
    blocks, drains, unclassified = group_applications(raw_rows, application_aliases, label_aliases)
    tub_room = any(re.match(r"Bathroom Type\s*/\s*(?:Shower\s*/\s*Tub\s+Combination|"
                           r"Tub\s+Combination|Tub\s*(?:and|&|/)\s*Shower(?:\s+Combination)?|"
                           r"Shower\s*(?:and|&)\s*Tub(?:\s+Combination)?)\s*$",
                           " ".join(row["type_description"].split()), re.IGNORECASE)
                   for row in raw_rows)

    output = []

    def add(kind, size, description, qty):
        unit = qty.split()[-1] if qty else ""
        output.append([kind, size, description, "", unit])

    for drain in drains:
        finish = drain.get("finish", "")
        code = re.search(r"\[[^]]+\]", finish)
        finish = re.sub(r"\s*\[[^]]+\]", "", finish).strip()
        add("Shower Drain", code.group() if code else "",
            "- ".join(value for value in (drain.get("shape", ""), finish) if value),
            drain.get("unit", ""))
        # Explicit accessory rule: one riser plug for each shower drain.
        output.append(["Drain riser plug", "", "Drain riser plug", 1, "EA"])

    # Presentation preferences only; these never determine detection/membership.
    priority = {"shower_wall": 0, "shower_wall_area": 0, "shower_floor": 1, "floor": 2}
    for block in sorted(blocks, key=lambda b: priority.get(b.get("kind"), 3)):
        application = block.get("kind")
        caulk_required = (
            application == "backsplash"
            or (tub_room and application in {"shower_wall", "floor"})
        )
        for text, qty in block["selections"]:
            size, description = product_fields(text, label_aliases)
            add(block["type"], size, description, qty)
        # Accessories remain attached to their application, including when a
        # block contains multiple material selections. Do not duplicate them.
        accessories = []
        for text, qty in block["accessories"]:
            category, value = field(text, label_aliases)
            if category == "schluter":
                description = value
                accessories.append((0, "Schluter", "", description, qty))
            elif category == "niche":
                size = size_match(text)
                dimensions = size.group().strip() if size else ""
                dimensions = re.sub('[\u201c\u201d\ufffd\u2033]', '"', dimensions)
                accessories.append((1, "Schluter niche", dimensions,
                                    "Schluter niche", qty))
            elif category == "corner_shelf":
                code = re.search(r"\[[^]]+\]", value)
                description = re.sub(r"^Corner Shelf\s*/\s*", "", value, flags=re.I)
                description = re.sub(r"\[[^]]+\]", "", description).strip()
                accessories.append((1, "Corner Shelf", code.group() if code else "", description, qty))
            elif category == "supply":
                kind = "Sealer" if re.match(r"sealer\b", text, re.I) else "Grout Release"
                accessories.append((3, kind, "", value, qty))
            else:
                accessories.append((2, "Grout", "", value, qty))
        for text, qty in block.get("accents", []):
            size, description = product_fields(text, label_aliases)
            accessories.append((1.5, "Accent", size, description, qty))
        if block.get("stone") and not any(a[1] == "Sealer" for a in accessories):
            # Approved reusable rule for explicitly identified stone, not names
            # such as "marble" that can describe porcelain lookalikes.
            accessories.append((3, "Sealer", "", "Sealer", ""))
        for _, kind, size, description, qty in sorted(accessories, key=lambda a: a[0]):
            add(kind, size, description, qty)
            if kind == "Grout" and caulk_required and description.strip():
                output.append(["Caulk", "", f"{description.strip()} sanded", "", "PCS"])
    for text, qty in unclassified:
        add("Unclassified (review)", "", text, qty)
    return output


def print_table(rows):
    headers = ["Type", "Size/Area", "Description", "Quantity", "Units"]
    # Escaping keeps literal source pipes from introducing extra columns.
    cells = [[str(value).replace("|", r"\|") for value in row] for row in [headers, *rows]]
    widths = [max(3, *(len(row[i]) for row in cells)) for i in range(len(headers))]
    def line(row):
        return "| " + " | ".join(value.ljust(width) for value, width in zip(row, widths)) + " |"
    print(line(cells[0]))
    print(line(["-" * width for width in widths]))
    for row in cells[1:]:
        print(line(row))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("room", help="Room code to extract; quote codes containing spaces")
    parser.add_argument("--aliases", type=Path,
                        help="Optional JSON with application_aliases and label_aliases mappings")
    args = parser.parse_args()
    try:
        applications, labels = dict(APPLICATION_ALIASES), dict(LABEL_ALIASES)
        if args.aliases:
            config = json.loads(args.aliases.read_text(encoding="utf-8"))
            if not isinstance(config, dict) or set(config) - {"application_aliases", "label_aliases"}:
                raise ValueError("Aliases must contain application_aliases and/or label_aliases")
            for key, destination in [("application_aliases", applications), ("label_aliases", labels)]:
                additions = config.get(key, {})
                if not isinstance(additions, dict) or any(
                        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
                        for k, v in additions.items()):
                    raise ValueError(f"{key} must map nonempty labels to nonempty category names")
                if key == "label_aliases" and set(additions.values()) - {
                        "selection", "drain_shape", "drain_finish", "grout_color", "schluter",
                        "niche_reference", "context"}:
                    raise ValueError("Unsupported label_aliases category")
                destination.update({normalized(k): v for k, v in additions.items()})
        output = extract(args.pdf, args.room)
        rendered = table_rows(output["rows"], applications, labels)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(json.dumps(output, indent=2, ensure_ascii=True))
    print(f"\n{output['selected_room']}\n")
    print_table(rendered)


if __name__ == "__main__":
    main()
