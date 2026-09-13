"""Inspect Classica vendor-order columns without project rules.

Usage: uv run python scripts/extract_classica_room.py path/to/vendor-order.pdf ROOM_CODE
Prints all room codes, selected-room JSON, and a five-column table.
"""

import argparse
import json
import re
from pathlib import Path

import pdfplumber

if __package__:
    from .rules import merge_rules, rules_for
else:
    from rules import merge_rules, rules_for


def quantity_pattern(rules):
    units = "|".join(re.escape(unit) for unit in rules["units"]["accepted"])
    return re.compile(rf"\d+(?:[.,]\d+)?\s+(?:{units})", re.I)


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


def extract(path, target=None, apply_revisions=True, rules=None):
    rules = rules_for(rules)
    qty_re = quantity_pattern(rules)
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
                extraction_stops = [*rules["change_orders"]["stop_headings"],
                                    *rules["change_orders"]["approved_headings"], "Change Order #"]
                if any(text.casefold().startswith(value.casefold()) for value in extraction_stops):
                    return finish_extraction(pdf, rooms, records, target, apply_revisions, rules)
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
                if qty and not qty_re.fullmatch(qty):
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
        return finish_extraction(pdf, rooms, records, target, apply_revisions, rules)


def finish_extraction(pdf, rooms, records, target, apply_revisions=True, rules=None):
    if __package__:
        from .changes import apply_changes, read_changes
    else:
        from changes import apply_changes, read_changes
    rules = rules_for(rules)
    instructions = read_changes("\n".join(page.extract_text() or "" for page in pdf.pages), rules)
    report = apply_changes(records, instructions, rules) if apply_revisions else []
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
def normalized(text):
    return " ".join(text.split()).casefold()


# Backward-compatible views; values are loaded from the editable rules file.
APPLICATION_ALIASES = rules_for()["applications"]["aliases"]
LABEL_ALIASES = rules_for()["fields"]["aliases"]


def application_kind(text, rules=None):
    rules = rules_for(rules)
    return rules["applications"]["aliases"].get(
        normalized(re.split(r"\s*/\s*", text, maxsplit=1)[0]))


def field(text, rules=None):
    """Normalize labels, preserving the spelling of their values."""
    rules = rules_for(rules)
    for pattern in rules["fields"]["selection_patterns"]:
        match = re.match(pattern, text, re.I)
        if match:
            return "selection", text[match.end():].strip()
    label, separator, value = text.partition(":")
    key = normalized(label)
    value = value.lstrip(": ")
    if separator:
        kind = rules["fields"]["aliases"].get(key)
        if kind:
            return kind, value
        if any(key == prefix or key.startswith(prefix + " ")
               for prefix in rules["fields"]["material_prefixes"]):
            return "context", value
        if any(key.startswith(prefix) for prefix in rules["fields"]["schluter_prefixes"]):
            # Remove an optional applicability qualifier, not product colons.
            value = re.sub(r"^\([^)]*\)\s*:\s*", "", value)
            return "schluter", value
    value_normalized = normalized(text)
    if any(value_normalized.startswith(prefix) for prefix in rules["fields"]["niche_prefixes"]):
        return "niche", text
    if any(value_normalized.startswith(prefix) for prefix in rules["fields"]["corner_shelf_prefixes"]):
        return "corner_shelf", text
    if any(value_normalized == prefix or value_normalized.startswith(prefix + ":")
           or value_normalized.startswith(prefix + " /")
           for prefix in rules["fields"]["supply_prefixes"]):
        return "supply", text
    if any(value_normalized.startswith(prefix) for prefix in rules["fields"]["context_prefixes"]):
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
def application_summary(text, rules=None):
    """Read compact product/grout/trim summaries emitted by some orders."""
    rules = rules_for(rules)
    match = re.match(rules["recognition"]["compact_summary_pattern"], text, re.I)
    return match.groupdict() if match else None


def is_note(text, rules):
    value = normalized(text)
    return re.match(r"\d+ rows\b", value) or any(
        value.startswith(prefix.casefold())
        for prefix in rules["recognition"]["note_prefixes"]
    )


def group_applications(raw_rows, rules=None):
    """Recognize application headings; isolate unknown headings for review."""
    rules = rules_for(rules)
    sections = []
    for row in raw_rows:
        if row.get("excluded_by_change"):
            continue
        text = " ".join(row["type_description"].split())
        item = (text, row["qty"])
        accessory_context = sections and sections[-1]["heading"] and field(
            sections[-1]["heading"][0], rules)[0] in {"niche", "corner_shelf"}
        note = not row["qty"] and ((is_note(text, rules)
                                      and not application_kind(text, rules))
                                     or application_summary(text, rules) or (
            accessory_context and not application_kind(text, rules)))
        if row.get("layout", {}).get("is_heading") and not note:
            sections.append({"heading": item, "children": []})
        elif sections:
            sections[-1]["children"].append(item)
        else:
            sections.append({"heading": None, "children": [item]})

    blocks, drains, unclassified, niches, shelves = [], [], [], [], []
    for section in sections:
        heading = section["heading"]
        children = section["children"]
        selections = [item for item in children if field(item[0], rules)[0] == "selection"]
        summaries = [(item, application_summary(item[0], rules)) for item in children]
        summaries = [(item, summary) for item, summary in summaries if summary]
        canonical = application_kind(heading[0], rules) if heading else None
        thin_brick = heading and canonical == "surround" and re.search(
            rules["recognition"]["thin_brick_pattern"], heading[0], re.I)
        if thin_brick:
            details = "; ".join(text for text, _ in children if re.match(
                rules["recognition"]["thin_brick_detail_pattern"], text, re.I))
            selections = [("AREA A SELECTION: Thin Brick" + ("; " + details if details else ""), heading[1])]
        if canonical and selections:
            # Some PDFs replace product detail with a compact heading and leave
            # only "Tile (...) Group 2" in AREA A SELECTION. Recover only the
            # values stated by that summary; absent size/profile details stay blank.
            if len(summaries) == 1:
                summary = summaries[0][1]
                selections = [
                    ("AREA A SELECTION: " + summary["product"], qty)
                    if re.fullmatch(rules["recognition"]["generic_product_pattern"],
                                    field(text, rules)[1], re.I)
                    else (text, qty)
                    for text, qty in selections
                ]
            pattern = next((text.split(":", 1)[1].strip() for text, _ in children
                            if normalized(text).startswith("pattern:")), "")
            block = {"type": heading[0], "kind": canonical, "heading_qty": heading[1],
                     "pattern": pattern,
                     "selections": selections, "accessories": [],
                     "stone": any(re.search(rules["recognition"]["stone_material_pattern"], text, re.I)
                                  for text, _ in children)}
            blocks.append(block)
        else:
            block = None
        if heading and field(heading[0], rules)[0] == "corner_shelf":
            details = [text for text, _ in children if re.search(r"\bshelf\b", text, re.I)]
            shelves.append(("Corner Shelf / " + " / ".join(details or [heading[0]]), heading[1]))
            unclassified.extend((text, qty) for text, qty in children if text not in details)
            continue
        section_drain = None
        for text, qty in ([heading] if heading else []) + children:
            category, value = field(text, rules)
            summary = application_summary(text, rules)
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
                if qty:
                    section_drain["qty"] = qty
            elif category == "niche":
                reference = next((re.sub(r"^same\s+as\s+", "", value, flags=re.IGNORECASE)
                                  for child, _ in children
                                  for kind, value in [field(child, rules)]
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
            interior = [b for b in blocks if reference and application_kind(reference, rules)
                        and b.get("kind") == application_kind(reference, rules)]
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


def product_fields(text, rules=None):
    rules = rules_for(rules)
    description = field(text, rules)[1]
    description = re.sub(rules["recognition"]["product_group_prefix_pattern"],
                         "", description, flags=re.I)
    size = size_match(description)
    if size:
        description = description[:size.start()] + description[size.end():]
    description = re.sub(r"\s*:\s*", ", ", description)
    description = re.sub(r",\s*,", ",", description).strip(" ,")
    description = re.sub(r"\s+,", ",", description)
    return size.group().strip() if size else "", description


def parse_quantity(value, rules):
    if not value:
        return None, ""
    match = quantity_pattern(rules).fullmatch(value.strip())
    if not match:
        return None, ""
    number, unit = value.rsplit(maxsplit=1)
    number = float(number.replace(",", "."))
    if number.is_integer():
        number = int(number)
    unit = rules["units"]["normalize"].get(unit.upper(), unit.upper())
    return number, unit


def _dimension(value):
    value = value.strip().replace("¼", " 1/4").replace("½", " 1/2").replace("¾", " 3/4")
    if not value:
        return None
    pieces = re.split(r"[xX×]", value)
    dimensions = []
    for piece in pieces[:2]:
        values = re.findall(r"\d+(?:\.\d+)?(?:/\d+)?", piece)
        total = 0.0
        for item in values:
            if "/" in item:
                numerator, denominator = item.split("/", 1)
                total += float(numerator) / float(denominator)
            else:
                total += float(item)
        if values:
            dimensions.append(total)
    return max(dimensions) if len(dimensions) == 2 else None


def waste_percent(size, pattern, description, application, rules):
    haystack = normalized(" ".join((pattern, description)))
    dimension = _dimension(size)
    for rule in rules["quantity"]["waste_rules"]:
        if rule.get("applications") and application not in rule["applications"]:
            continue
        if rule.get("any_keywords") and not any(
                keyword.casefold() in haystack for keyword in rule["any_keywords"]):
            continue
        if rule.get("all_keyword_groups") and not all(
                any(keyword.casefold() in haystack for keyword in group)
                for group in rule["all_keyword_groups"]):
            continue
        if rule.get("min_dimension") is not None and (
                dimension is None or dimension < rule["min_dimension"]):
            continue
        return rule["percent"]
    raise ValueError("Classica quantity rules did not provide a default waste rule")


def _format_number(value):
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def structured_rows(raw_rows, rules=None):
    """Return configured Classica rows with quantities and audit metadata."""
    rules = rules_for(rules)
    blocks, drains, unclassified = group_applications(raw_rows, rules)
    recognition = rules["recognition"]
    tub_room = any(
        normalized(row["type_description"]).startswith("bathroom type /")
        and any(phrase.casefold() in normalized(row["type_description"])
                for phrase in recognition["tub_room_phrases"])
        for row in raw_rows
    )
    display = rules["accessories"]["display"]
    purchasable = set(rules["accessories"]["purchasable_categories"])
    output = []

    def add(kind, size, description, source_qty="", *, category="", application="",
            measured=None, waste=None, comments="", pattern="", source="", unit_override=""):
        quantity, unit = parse_quantity(source_qty, rules)
        unit = unit_override or unit
        if category not in purchasable:
            quantity = None
        if category in rules["accessories"]["selection_only_categories"]:
            unit = ""
        formula = ""
        if measured is not None and waste is not None:
            formula = rules["quantity"]["formula_template"].format(
                measured=_format_number(measured), waste=_format_number(waste))
            comments = rules["quantity"]["review_comment_template"].format(
                measured=_format_number(measured), waste=_format_number(waste), unit=unit or "SF")
            quantity = formula
            unit = unit or "SF"
        output.append({"type": kind, "size": size, "description": description,
                       "quantity": quantity if quantity is not None else "", "unit": unit,
                       "measured_qty": measured, "waste_percent": waste,
                       "formula": formula, "comments": comments, "pattern": pattern,
                       "application": application, "source": source})

    for drain in drains:
        finish = drain.get("finish", "")
        code = re.search(r"\[[^]]+\]", finish)
        finish = re.sub(r"\s*\[[^]]+\]", "", finish).strip()
        add(display["drain"], code.group() if code else "",
            "- ".join(value for value in (drain.get("shape", ""), finish) if value),
            drain.get("qty", ""), category="drain")
        riser = rules["accessories"]["drain_riser"]
        if riser.get("enabled"):
            output.append({"type": riser["type"], "size": "", "description": riser["description"],
                           "quantity": riser["quantity"], "unit": riser["unit"],
                           "measured_qty": None, "waste_percent": None, "formula": "",
                           "comments": "", "pattern": "", "application": "", "source": ""})

    presentation = rules["applications"]["presentation"]
    for block in sorted(blocks, key=lambda item: presentation.get(
            item.get("kind"), {"priority": 999})["priority"]):
        application = block.get("kind", "")
        caulk = rules["accessories"]["caulk"]
        caulk_required = application in caulk["applications"] or (
            tub_room and application in caulk["tub_applications"])
        pattern = block.get("pattern", "")
        heading_qty, heading_unit = parse_quantity(block.get("heading_qty", ""), rules)
        unique_measurement = len(block["selections"]) == 1 and heading_qty is not None and heading_unit == "SF"
        for text, source_qty in block["selections"]:
            size, description = product_fields(text, rules)
            if unique_measurement:
                waste = waste_percent(size, pattern, description, application, rules)
                add(block["type"], size, description, source_qty, application=application,
                    measured=heading_qty, waste=waste, pattern=pattern, source=text)
            else:
                add(block["type"], size, description, source_qty, application=application,
                    comments=rules["quantity"]["ambiguous_comment"], pattern=pattern, source=text)

        accessories = []
        accessory_order = rules["accessories"]["order"]
        for text, source_qty in block["accessories"]:
            category, value = field(text, rules)
            if category == "schluter":
                accessories.append((accessory_order["schluter"], display["schluter"], "", value, source_qty, "schluter"))
            elif category == "niche":
                size = size_match(text)
                dimensions = size.group().strip() if size else ""
                dimensions = re.sub('[\u201c\u201d\ufffd\u2033]', '"', dimensions)
                accessories.append((accessory_order["niche"], display["niche"], dimensions,
                                    display["niche"], source_qty, "niche"))
            elif category == "corner_shelf":
                code = re.search(r"\[[^]]+\]", value)
                description = re.sub(r"^Corner Shelf\s*/\s*", "", value, flags=re.I)
                description = re.sub(r"\[[^]]+\]", "", description).strip()
                accessories.append((accessory_order["corner_shelf"], display["corner_shelf"], code.group() if code else "",
                                    description, source_qty, "corner_shelf"))
            elif category == "supply":
                supply = "sealer" if normalized(text).startswith("sealer") else "grout_release"
                accessories.append((accessory_order[supply], display[supply], "", value, source_qty, supply))
            else:
                accessories.append((accessory_order["grout"], display["grout"], "", value, source_qty, "grout"))
        for text, source_qty in block.get("accents", []):
            size, description = product_fields(text, rules)
            accessories.append((accessory_order["accent"], presentation["accent"]["display"], size,
                                description, source_qty, "accent"))
        sealer = rules["accessories"]["sealer"]
        if block.get("stone") and not any(item[5] == "sealer" for item in accessories):
            accessories.append((accessory_order["sealer"], sealer["type"], "", sealer["description"], "", "sealer"))
        for _, kind, size, description, source_qty, category in sorted(accessories, key=lambda item: item[0]):
            add(kind, size, description, source_qty, category=category, application=application,
                source=description)
            if category == "grout" and caulk_required and description.strip():
                add(display["caulk"], "", description.strip() + caulk["description_suffix"],
                    "", category="caulk", application=application, unit_override=caulk["unit"])
    review = rules["review"]
    for text, source_qty in unclassified:
        add(review["unclassified_type"], "", text, source_qty,
            comments=review["required_comment"], source=text)
    return output


def table_rows(raw_rows, rules=None, label_aliases=None):
    """Render the shared five-column Classica table."""
    # Backward compatibility for the former table_rows(rows, applications, labels) API.
    if rules is not None and "schema_version" not in rules:
        overrides = {"applications": {"aliases": rules}}
        if label_aliases is not None:
            overrides["fields"] = {"aliases": label_aliases}
        rules = merge_rules(rules_for(), overrides)
    return [[row["type"], row["size"], row["description"], row["quantity"], row["unit"]]
            for row in structured_rows(raw_rows, rules)]


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
        rules = rules_for()
        if args.aliases:
            config = json.loads(args.aliases.read_text(encoding="utf-8"))
            if not isinstance(config, dict) or set(config) - {"application_aliases", "label_aliases"}:
                raise ValueError("Aliases must contain application_aliases and/or label_aliases")
            overrides = {}
            for key, destination in [("application_aliases", ("applications", "aliases")),
                                     ("label_aliases", ("fields", "aliases"))]:
                additions = config.get(key, {})
                if not isinstance(additions, dict) or any(
                        not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
                        for k, v in additions.items()):
                    raise ValueError(f"{key} must map nonempty labels to nonempty category names")
                if key == "label_aliases" and set(additions.values()) - set(rules["fields"]["categories"]):
                    raise ValueError("Unsupported label_aliases category")
                overrides.setdefault(destination[0], {})[destination[1]] = {
                    normalized(k): v for k, v in additions.items()}
            rules = merge_rules(rules, overrides)
        output = extract(args.pdf, args.room, rules=rules)
        rendered = table_rows(output["rows"], rules)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(json.dumps(output, indent=2, ensure_ascii=True))
    print(f"\n{output['selected_room']}\n")
    print_table(rendered)


if __name__ == "__main__":
    main()
