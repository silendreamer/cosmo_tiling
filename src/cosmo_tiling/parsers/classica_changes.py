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
    tile_instructions = [entry for entry in instructions if re.match(
        r"(?:Tile\b|Tile Floor\b|Floor Tile\b|Backsplash\b|Shower Wall\b|Wall Niche\b|Shower Drain\b|Fireplace Surround\b)",
        entry["text"], re.I)]
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


def application_kind(text):
    value = " ".join(text.split()).casefold()
    if "niche" in value:
        return "niche"
    if "shower drain" in value or "linear drain" in value:
        return "drain"
    if "backsplash" in value or "back splash" in value:
        return "backsplash"
    if "back wall only above countertop" in value or "between hutches" in value:
        return "backsplash"
    if re.search(r"(?:floor tile|tile floor)", value):
        return "floor"
    if any(label in value for label in ("shower wall", "wall tile", "main back wall", "side walls")):
        return "shower_wall"
    if "surround" in value:
        return "surround"
    return None


def room_matches(text, room):
    if scope_matches(text, room, ""):
        return True
    value, code = text.casefold(), room.casefold()
    aliases = [
        (r"\bguest suite\b", r"\(s\)_g$"),
        (r"\bbutler'?s pantry\b", r"^bpantry$"),
        (r"\bscullery\b", r"^scullery$"),
        (r"\blaundry(?: room)?\s*(?:1st floor|one)?\b", r"^lndry1$"),
        (r"\bpowder room\b", r"^bthpowder"),
        (r"\bfireplace\b", r"^great"),
    ]
    return any(re.search(label, value) and re.search(pattern, code) for label, pattern in aliases)


def placeholder_contexts(records):
    contexts = []
    active = {}
    for index, record in enumerate(records):
        room = record["room"]
        text = " ".join(record["type_description"].split())
        if "see change order" in text.casefold():
            context = active.get(room)
            if context:
                explicit_kind = application_kind(text)
                contexts.append({**context, "application": explicit_kind or context["application"],
                                 "placeholder": index,
                                 "order_ref": (int(match.group(1)) if (
                                     match := re.search(r"change order\s*#\s*(\d+)", text, re.I)) else None)})
            continue
        kind = application_kind(text) if record.get("layout", {}).get("is_heading") else None
        if kind:
            active[room] = {"room": room, "application": kind, "heading": index}
    return contexts


def _product(segment):
    value = " ".join(segment.split()).strip(" .;-")
    tile = re.search(r"(?:\(?Tile\)?\s*[:;]\s*)?Group\s+[^:\-]+\s*[:\-]\s*(.+)", value, re.I)
    if tile:
        value = tile.group(1)
    value = re.split(r"\s+-\s+(?:Grout|Schluter|NOTE)\b", value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r"\s*[.;]?\s*PATTERN\s*:.*$", "", value, flags=re.I)
    return value.strip(" .;-")


ZONE_RE = re.compile(
    r"(?:^|\s+-\s+)(MAIN BACK WALL|BENCH TOP|SIDE WALLS(?:\s*&\s*FRONT OF BENCH)?)\b", re.I)


def wall_rows(instructions):
    zones, grout, schluter = [], "", ""
    for instruction in instructions:
        text = " ".join(instruction["text"].split())
        matches = list(ZONE_RE.finditer(text))
        for position, match in enumerate(matches):
            end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            segment = text[match.end():end]
            product = _product(segment)
            if product and not re.match(r"^(?:pattern|tile)\s*:$", product, re.I):
                labels = {"main back wall": "Main Back wall", "side walls": "Side walls",
                          "bench top": "Bench top",
                          "side walls & front of bench": "Side walls & front of bench"}
                label = labels[" ".join(match.group(1).casefold().split())]
                zones.append((label, product))
        grout_match = re.search(r"Grout(?: Color)?(?: for All Walls)?\s*:\s*(.+?)(?=\s+-\s+(?:Schluter|This Price)|\s+NOTE:|$)", text, re.I)
        trim_match = re.search(r"Schluter(?: Trim)?(?: Color)?(?: for All Walls(?: And Bench)?)?(?: For Bench)?\s*:\s*(.+?)(?=\s+NOTE:|$)", text, re.I)
        if grout_match:
            grout = grout_match.group(1).strip(" .;-")
        if trim_match:
            schluter = trim_match.group(1).strip(" .;-")
    by_label = {}
    for label, product in zones:
        if label in by_label and by_label[label] != product:
            return []
        by_label[label] = product
    unique = list(by_label.items())
    if not unique:
        return []
    rows = []
    for label, product in unique:
        rows.extend([(label, "", True), ("AREA A SELECTION: " + product, None, False)])
    if grout:
        rows.append(("GROUT COLOR: " + grout, "", False))
    if schluter:
        rows.append(("SCHLUTER: " + schluter, "", False))
    return rows


def floor_rows(instruction):
    text = " ".join(instruction.split())
    matches = list(re.finditer(r"Group\s+[^:\-]+\s*[:\-]\s*", text, re.I))
    products = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        product = re.split(r"\s+(?:AND\s+)?(?:-\s*)?(?:Grout|Schluter)\s*:",
                           text[match.end():end], maxsplit=1, flags=re.I)[0].strip(" .;-AND")
        if product:
            products.append(product)
    if not products:
        return []
    rows = [("Floor Tile", "", True)]
    rows.extend(("AREA A SELECTION: " + product, None, False) for product in products)
    grout = re.search(r"Grout(?: Color)?\s*:\s*(.+?)(?=\s+Schluter\s*:|\.|$)", text, re.I)
    trim = re.search(r"Schluter(?: Color)?\s*:\s*(.+?)(?=\.|$)", text, re.I)
    if grout:
        rows.append(("GROUT COLOR: " + grout.group(1).strip(), "", False))
    if trim:
        rows.append(("SCHLUTER: " + trim.group(1).strip(), "", False))
    return rows


def niche_rows(instruction):
    text = " ".join(instruction.split())
    product = re.search(r"(?:Grp|Group)\.?\s*\d+\s*[:\-]?\s*(.+?)(?=\s+-\s+(?:Running|Installed|Same)|$)", text, re.I)
    if not product:
        return []
    value = re.sub(r",?\s*same grout.*$", "", product.group(1), flags=re.I).strip(" .;-")
    return [("Niche tile", "", True), ("AREA A SELECTION: " + value, None, False)]


def backsplash_rows(instruction):
    text = " ".join(instruction.split())
    product = re.search(r"(?:Grp|Group|Tile Group)\.?\s*\d+\s*[:\-]\s*-?\s*(.+?)(?=\s+(?:Grout|PATTERN)\s*:|\s+Price includes|$)", text, re.I)
    if not product:
        return []
    rows = [("Backsplash", "", True),
            ("AREA A SELECTION: " + product.group(1).strip(" .;-"), None, False)]
    grout = re.search(r"Grout\s*:\s*(.+?)(?=\s+Schluter\s*:|;\s*Back wall|\s+Price includes|$)", text, re.I)
    if grout:
        rows.append(("GROUT COLOR: " + grout.group(1).strip(), "", False))
    return rows


def drain_rows(instruction):
    text = " ".join(instruction.split())
    payload = re.search(r"\s+-\s+(?:ADD|CHANGE|REPLACE)\s+-\s+(.+)$", text, re.I)
    value = payload.group(1) if payload else ""
    shape = re.search(r"\b((?:Linear|Square|Round)\s*(?:Drain)?)\b", value, re.I)
    if not shape:
        return []
    rows = [("SHOWER DRAIN: " + shape.group(1).strip(), "", False)]
    finish = re.search(r"(?:finish|color)\s*:\s*(.+?)(?=\s+-\s+|$)", value, re.I)
    if finish:
        rows.append(("SHOWER DRAIN FINISH: " + finish.group(1).strip(" .;-"), "", False))
    return rows


def surround_rows(instruction):
    text = " ".join(instruction.split())
    product = re.search(
        r"\s+-\s+ADD\s+-\s+(?:PATTERN\s*:.*?\s+-\s+)?(.+?)(?=\s+-\s+Grout\s*:|$)",
        text, re.I,
    )
    if not product:
        return []
    rows = [("Surround / Tile (full wall)", "", True),
            ("AREA A SELECTION: " + product.group(1).strip(" .;-"), None, False)]
    grout = re.search(r"\s+-\s+Grout\s*:\s*(.+?)(?=\s+-\s+Schluter\s*:|$)", text, re.I)
    trim = re.search(r"\s+-\s+Schluter\s*:\s*(.+?)$", text, re.I)
    if grout:
        rows.append(("GROUT COLOR: " + grout.group(1).strip(), "", False))
    if trim:
        rows.append(("SCHLUTER: " + trim.group(1).strip(), "", False))
    return rows


def resolve_placeholders(records, instructions, report):
    used = set()
    for context in placeholder_contexts(records):
        candidates = [(index, item) for index, item in enumerate(instructions)
                      if room_matches(item["text"], context["room"])
                      and application_kind(item["text"]) in {None, context["application"]}]
        if not candidates:
            report.append({"order": "", "text": records[context["placeholder"]]["type_description"],
                           "status": "review", "room": context["room"],
                           "application": context["application"],
                           "reason": "No matching approved change order"})
            continue
        generated = []
        if context["application"] == "shower_wall":
            generated = wall_rows([item for _, item in candidates])
        elif context["application"] == "floor":
            parsed = [(index, item, floor_rows(item["text"])) for index, item in candidates]
            parsed = [value for value in parsed if value[2]]
            if len(parsed) == 1:
                generated = parsed[0][2]
                for _, item in candidates:
                    clarification = re.search(
                        r"CLARIFICATION\s+-\s+(Grout|Schluter)(?: Color)?\s*:\s*(.+?)(?=\s+-\s+|$)",
                        item["text"], re.I)
                    if clarification:
                        row_type = "GROUT COLOR" if clarification.group(1).casefold() == "grout" else "SCHLUTER"
                        generated = [
                            (row_type + ": " + clarification.group(2).strip(), qty, heading)
                            if text.startswith(row_type + ":") else (text, qty, heading)
                            for text, qty, heading in generated
                        ]
        elif context["application"] == "niche":
            additions = [(index, item) for index, item in candidates
                         if re.search(r"\s+-\s+ADD\s+-\s+", item["text"], re.I)]
            if additions:
                latest_order = max(item["order"] for _, item in additions)
                latest = [(index, item) for index, item in additions if item["order"] == latest_order]
                if len(latest) == 1:
                    candidates = latest
                    generated = niche_rows(latest[0][1]["text"])
        elif context["application"] == "backsplash" and len(candidates) == 1:
            generated = backsplash_rows(candidates[0][1]["text"])
            if not generated:
                # An extension-only instruction changes placement, not selection.
                generated = [("", "", False)]
        elif context["application"] == "drain" and len(candidates) == 1:
            generated = drain_rows(candidates[0][1]["text"])
        elif context["application"] == "surround":
            additions = [(index, item) for index, item in candidates
                         if re.search(r"\s+-\s+ADD\s+-\s+", item["text"], re.I)]
            if len(additions) == 1:
                generated = surround_rows(additions[0][1]["text"])
        if not generated:
            for index, _ in candidates:
                report[index].update(room=context["room"], application=context["application"],
                                     reason="Matching instruction could not be parsed deterministically")
            continue

        heading = context["heading"]
        placeholder = context["placeholder"]
        end = placeholder + 1
        while end < len(records) and records[end]["room"] == context["room"]:
            if records[end].get("layout", {}).get("is_heading") and application_kind(
                    records[end]["type_description"]):
                break
            end += 1
        if context["application"] in {"shower_wall", "floor", "surround"} or (
                context["application"] == "backsplash" and generated != [("", "", False)]):
            for index in range(heading, end):
                records[index]["excluded_by_change"] = "Resolved from approved change order"
        else:
            records[placeholder]["excluded_by_change"] = "Resolved from approved change order"

        if generated != [("", "", False)]:
            qty = records[heading].get("qty", "")
            page = records[heading].get("layout", {}).get("page")
            for text, row_qty, is_heading in generated:
                records.append({"room": context["room"], "type_description": text,
                                "selection_changed": "", "qty": qty if row_qty is None else row_qty,
                                "layout": {"page": page, "is_heading": is_heading,
                                           "derived_from_change": True}})
        for index, item in candidates:
            used.add(index)
            report[index].update(status="applied", room=context["room"],
                                 application=context["application"],
                                 reason="Resolved matching See Change Order placeholder")
    return used


def apply_changes(records, instructions):
    sections = []
    for i, record in enumerate(records):
        if (not sections or record["room"] != records[sections[-1][0]]["room"]
                or record.get("layout", {}).get("is_heading")):
            sections.append([])
        sections[-1].append(i)
    report = [{**instruction, "status": "review", "application": application_kind(instruction["text"]) or "",
               "reason": "Unsupported or ambiguous instruction"} for instruction in instructions]
    used = resolve_placeholders(records, instructions, report)
    for instruction_index, instruction in enumerate(instructions):
        entry = report[instruction_index]
        if instruction_index in used:
            continue
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
                entry.update(status="applied", room=room, application="shower_wall",
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
            entry.update(status="applied", reason="Exact replacement", room=record["room"],
                         application=application_kind(scope) or application_kind(record["type_description"]) or "")
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
                     application=application_kind(scope) or application_kind(records[matched[0]]["type_description"]) or "",
                     reason="Source section excluded" if operation == "DELETE" else "ADD already represented by source section")
    # A numbered placeholder can point to complementary ADD/DELETE instructions
    # that the legacy exact matcher applied directly to existing source sections.
    for context in placeholder_contexts(records):
        if records[context["placeholder"]].get("excluded_by_change"):
            continue
        applied = [entry for entry in report if entry["status"] == "applied"
                   and entry.get("room") == context["room"]
                   and entry.get("application") == context["application"]
                   and (context["order_ref"] is None or entry["order"] == context["order_ref"])]
        if applied:
            records[context["placeholder"]]["excluded_by_change"] = "Resolved from approved change order"
    return report
