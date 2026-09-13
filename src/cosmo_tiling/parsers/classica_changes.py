"""Conservative changes supported by explicit scopes and unique source matches.

No approximate product matching: unsupported or ambiguous instructions remain
in the report for review. Existing source rows are retained for auditing.
"""
import re


def read_changes(text):
    instructions = []
    active = False
    found_changes = False
    number = 0
    current = None
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"Change Orders\s+Approved", line, re.I):
            active = True
            found_changes = True
            continue
        order = re.match(r"Change Order\s*#([1-9]\d*)", line, re.I)
        if order and found_changes:
            active = True
            number = int(order[1])
            current = None
            continue
        if line.startswith(("Included at Start", "Related Items from other Vendors")):
            active = False
            current = None
            continue
        if not active:
            continue
        if re.match(r"\d{1,2}/\d{1,2}/\d{4}\s+Lot\b", line):
            continue
        line = re.sub(r"\s+\d{1,2}/\d{1,2}/\d{4}$", "", line)
        if line.startswith(("\u2022", "\ufffd")):
            current = {"order": number, "text": line[1:].strip()}
            instructions.append(current)
        elif current and line:
            current["text"] += " " + line
    tile_instructions = [entry for entry in instructions
                         if not re.match(r"Structural\s+Op\w*\s*:", entry["text"], re.I)]
    return sorted(tile_instructions, key=lambda entry: entry["order"])


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def scope_matches(scope, room, heading):
    # Explicit room codes are the strongest available scope.
    if re.search(r"(?<!\w)" + re.escape(room) + r"(?!\w)", scope, re.I):
        return True
    bedroom = re.search(r"(?:bedroom|bed)\s*#?\s*(\d+)\b", scope, re.I)
    if bedroom:
        return bool(re.search(r"_BR" + bedroom[1] + r"S?$", room, re.I))
    if re.search(r"\b(?:primary|owner'?s)\b", scope, re.I):
        return bool(re.search(r"_(?:PRIM|OWN)(?:/|$)", room, re.I))
    if re.search(r"\bbasement\b", scope, re.I):
        return bool(re.search(r"_BASE$", room, re.I))
    if re.search(r"\bfireplace\b", scope, re.I):
        return bool(re.match(r"Surround\s*/", heading, re.I))
    if re.search(r"\bkitchen\b", scope, re.I):
        return room.upper().startswith("KITCHEN")
    return False


def split_wall_selection(instruction):
    """Extract explicitly labeled wall-area selections from change-order prose."""
    text = " ".join(instruction.split())
    main = re.search(
        r"(?:^|\s+-\s+)MAIN BACK WALL\s*[:\-]\s*(.+?)(?=\s+-\s+SIDE WALLS\s*[:\-])",
        text, re.I,
    )
    side = re.search(
        r"\s+-\s+SIDE WALLS\s*[:\-]\s*(.+?)(?=\s+-\s+Grout Color for All Walls\s*:)",
        text, re.I,
    )
    grout = re.search(
        r"\s+-\s+Grout Color for All Walls\s*:\s*(.+?)(?=\s+-\s+Schluter Trim Color for All Walls\s*:)",
        text, re.I,
    )
    schluter = re.search(
        r"\s+-\s+Schluter Trim Color for All Walls\s*:\s*(.+?)(?=\s+NOTE:|$)",
        text, re.I,
    )
    if not all((main, side, grout, schluter)):
        return None

    def product(segment):
        tile = re.search(r"\bTile\s*:\s*Group\s+[^:]+:\s*(.+)$", segment, re.I)
        value = tile.group(1) if tile else re.sub(r"^Group\s+[^:]+:\s*", "", segment, flags=re.I)
        return re.sub(r"\s*[.;]?\s*PATTERN\s*:.*$", "", value, flags=re.I).strip(" .;-")

    return {
        "main": product(main.group(1)),
        "side": product(side.group(1)),
        "grout": grout.group(1).strip(" .;-"),
        "schluter": schluter.group(1).strip(" .;-"),
    }


def apply_changes(records, instructions):
    sections = []
    for i, record in enumerate(records):
        if (not sections or record["room"] != records[sections[-1][0]]["room"]
                or record.get("layout", {}).get("is_heading")):
            sections.append([])
        sections[-1].append(i)
    report = []
    for instruction in instructions:
        entry = {**instruction, "status": "review", "reason": "Unsupported or ambiguous instruction"}
        report.append(entry)
        wall = (None if re.search(r"\s+-\s+(?:ADD|DELETE|REPLACE)\s+-\s+",
                                  instruction["text"], re.I)
                else split_wall_selection(instruction["text"]))
        if wall:
            scope = re.split(r"\s+-\s+(?:Upgrade|Change)\b", instruction["text"],
                             maxsplit=1, flags=re.I)[0]
            eligible = [section for section in sections
                        if scope_matches(scope, records[section[0]]["room"],
                                         records[section[0]]["type_description"])
                        and re.fullmatch(r"Shower Wall Tile", records[section[0]]["type_description"], re.I)]
            if len(eligible) == 1:
                matched = eligible[0]
                cursor = matched[-1] + 1
                while cursor < len(records) and records[cursor]["room"] == records[matched[0]]["room"]:
                    candidate = records[cursor]
                    if candidate.get("layout", {}).get("is_heading") and not re.match(
                            r"\*?See\s+Change Order", candidate["type_description"], re.I):
                        break
                    matched.append(cursor)
                    cursor += 1
                room = records[matched[0]]["room"]
                qty = records[matched[0]]["qty"]
                for i in matched:
                    records[i]["excluded_by_change"] = instruction["text"]
                page = records[matched[0]].get("layout", {}).get("page")
                synthetic = [
                    ("Main Back wall", "", True),
                    ("AREA A SELECTION: " + wall["main"], qty, False),
                    ("Side walls", "", True),
                    ("AREA A SELECTION: " + wall["side"], qty, False),
                    ("GROUT COLOR: " + wall["grout"], "", False),
                    ("SCHLUTER: " + wall["schluter"], "", False),
                ]
                records.extend({"room": room, "type_description": text,
                                "selection_changed": "", "qty": row_qty,
                                "layout": {"page": page, "is_heading": heading,
                                           "derived_from_change": instruction["order"]}}
                               for text, row_qty, heading in synthetic)
                entry.update(status="applied", room=room,
                             reason="Explicit main-wall and side-wall selections")
                continue
        action = re.match(r"(.+?)\s+-\s+(ADD|DELETE|REPLACE)\s+-\s+(.+)$", instruction["text"], re.I)
        if not action:
            continue
        scope, operation, payload = action.groups()
        operation = operation.upper()
        eligible = [section for section in sections if scope_matches(
            scope, records[section[0]]["room"], records[section[0]]["type_description"])]
        if operation == "REPLACE":
            replacement = re.fullmatch(r'"(.+?)"\s+WITH\s+"(.+?)"', payload, re.I)
            if not replacement:
                continue
            old, new = replacement.groups()
            matches = [i for section in eligible for i in section
                       if not records[i].get("excluded_by_change") and
                       records[i]["type_description"].count(old) == 1]
            if len(matches) != 1:
                entry["reason"] = "Replacement must match one scoped source row exactly"
                continue
            record = records[matches[0]]
            record.setdefault("original_description", record["type_description"])
            record["type_description"] = record["type_description"].replace(old, new, 1)
            entry.update(status="applied", reason="Exact replacement", room=record["room"])
            continue
        # Heading words must all be present in the explicit payload, rather than
        # accepting a fuzzy similarity score or guessing from the project name.
        matches = [section for section in eligible
                   if len(tokens(records[section[0]]["type_description"])) >= 2
                   and tokens(records[section[0]]["type_description"]) <= tokens(payload)
                   and tokens(payload) <= tokens(" ".join(records[i]["type_description"] for i in section))]
        if len(matches) != 1:
            entry["reason"] = "No unique scoped source section; manual review required"
            continue
        matched = matches[0]
        for i in matched:
            if operation == "DELETE":
                records[i]["excluded_by_change"] = instruction["text"]
            else:
                records[i].pop("excluded_by_change", None)
        entry.update(status="applied", room=records[matched[0]]["room"],
                     reason="Source section excluded" if operation == "DELETE" else "ADD already represented by source section")
    return report
