"""Conservative changes supported by explicit scopes and unique source matches.

No approximate product matching: unsupported or ambiguous instructions remain
in the report for review. Existing source rows are retained for auditing.
"""
import re

from .classica_rules import rules_for


def read_changes(text, rules=None):
    rules = rules_for(rules)
    config = rules["change_orders"]
    instructions = []
    active = False
    found_changes = False
    number = 0
    current = None
    for line in text.splitlines():
        line = line.strip()
        if any(line.casefold().startswith(value.casefold())
               for value in config["approved_headings"]):
            active = True
            found_changes = True
            continue
        order = re.match(r"Change Order\s*#([1-9]\d*)", line, re.I)
        if order and found_changes:
            active = True
            number = int(order[1])
            current = None
            continue
        if any(line.casefold().startswith(value.casefold()) for value in config["stop_headings"]):
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
    tile_instructions = [entry for entry in instructions if any(
        entry["text"].casefold().startswith(prefix.casefold())
        for prefix in config["instruction_prefixes"])]
    return sorted(tile_instructions, key=lambda entry: entry["order"])


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def scope_matches(scope, room, heading, rules=None):
    rules = rules_for(rules)
    # Explicit room codes are the strongest available scope.
    if re.search(r"(?<!\w)" + re.escape(room) + r"(?!\w)", scope, re.I):
        return True
    for configured in rules["change_orders"]["scope_patterns"]:
        match = re.search(configured["scope_pattern"], scope, re.I)
        if not match:
            continue
        target = room if configured["target"] == "room" else heading
        target_pattern = configured["target_pattern"].format(*match.groups())
        return bool(re.search(target_pattern, target, re.I))
    return False


def application_kind(text, rules=None):
    rules = rules_for(rules)
    value = " ".join(text.split()).casefold()
    return next((category for phrase, category in sorted(
                 rules["change_orders"]["application_phrases"].items(),
                 key=lambda item: len(item[0]), reverse=True)
                 if phrase.casefold() in value), None)


def room_matches(text, room, rules=None):
    rules = rules_for(rules)
    if scope_matches(text, room, "", rules):
        return True
    value, code = text.casefold(), room.casefold()
    return any(alias["phrase"].casefold() in value
               and re.search(alias["room_pattern"], code, re.I)
               for alias in rules["change_orders"]["room_scope_aliases"])


def placeholder_contexts(records, rules=None):
    rules = rules_for(rules)
    contexts = []
    active = {}
    for index, record in enumerate(records):
        room = record["room"]
        text = " ".join(record["type_description"].split())
        if "see change order" in text.casefold():
            context = active.get(room)
            if context:
                explicit_kind = application_kind(text, rules)
                contexts.append({**context, "application": explicit_kind or context["application"],
                                 "placeholder": index,
                                 "order_ref": (int(match.group(1)) if (
                                     match := re.search(r"change order\s*#\s*(\d+)", text, re.I)) else None)})
            continue
        kind = application_kind(text, rules) if record.get("layout", {}).get("is_heading") else None
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


def wall_rows(instructions, rules=None):
    rules = rules_for(rules)
    zone_labels = rules["change_orders"]["zone_labels"]
    zone_re = re.compile(
        r"(?:^|\s+-\s+)(" + "|".join(
            re.escape(label) for label in sorted(zone_labels, key=len, reverse=True)
        ) + r")\b", re.I)
    zones, grout, schluter = [], "", ""
    for instruction in instructions:
        text = " ".join(instruction["text"].split())
        matches = list(zone_re.finditer(text))
        for position, match in enumerate(matches):
            end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            segment = text[match.end():end]
            product = _product(segment)
            if product and not re.match(r"^(?:pattern|tile)\s*:$", product, re.I):
                label = zone_labels[" ".join(match.group(1).casefold().split())]
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


def single_wall_rows(instruction):
    """Parse a one-material wall ADD that supersedes older zoned selections."""
    text = " ".join(instruction.split())
    action = re.search(r"\s+-\s+ADD\s+-\s+(.+)$", text, re.I)
    if not action:
        return []
    product = _product(action.group(1))
    if not product:
        return []
    rows = [("Shower Wall Tile", "", True)]
    pattern = re.search(r"PATTERN\s*:\s*(.+?)(?=\s+-\s+(?:\(?Tile\)?|GROUP)\b)",
                        action.group(1), re.I)
    if pattern:
        rows.append(("PATTERN: " + pattern.group(1).strip(" .;-"), "", False))
    rows.append(("AREA A SELECTION: " + product, None, False))
    grout = re.search(r"\s+-\s+Grout(?: Color)?\s*:\s*(.+?)(?=\s+-\s+Schluter\s*:|$)", text, re.I)
    trim = re.search(r"\s+-\s+Schluter\s*:\s*(.+?)(?=\s+NOTE:|$)", text, re.I)
    if grout:
        rows.append(("GROUT COLOR: " + grout.group(1).strip(" .;-"), "", False))
    if trim:
        rows.append(("SCHLUTER: " + trim.group(1).strip(" .;-"), "", False))
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


def resolve_placeholders(records, instructions, report, rules=None):
    rules = rules_for(rules)
    used = set()
    for context in placeholder_contexts(records, rules):
        candidates = [(index, item) for index, item in enumerate(instructions)
                      if room_matches(item["text"], context["room"], rules)
                      and application_kind(item["text"], rules) in {None, context["application"]}]
        if not candidates:
            report.append({"order": "", "text": records[context["placeholder"]]["type_description"],
                           "status": "review", "room": context["room"],
                           "application": context["application"],
                           "reason": "No matching approved change order"})
            continue
        all_candidates = list(candidates)
        superseded = set()
        generated = []
        if context["application"] == "shower_wall":
            actions = [(index, item) for index, item in candidates if re.search(
                r"\s+-\s+(?:ADD|DELETE|REPLACE|CHANGE)\s+-\s+", item["text"], re.I)]
            if actions:
                latest_order = max(item["order"] for _, item in actions)
                candidates = [(index, item) for index, item in actions if item["order"] == latest_order]
                additions = [(index, item) for index, item in candidates if re.search(
                    r"\s+-\s+ADD\s+-\s+", item["text"], re.I)]
                if len(additions) == 1:
                    generated = single_wall_rows(additions[0][1]["text"])
                superseded = {index for index, item in all_candidates if item["order"] < latest_order}
            else:
                generated = wall_rows([item for _, item in candidates], rules)
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
                    superseded = {index for index, item in all_candidates if item["order"] < latest_order}
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
                    records[end]["type_description"], rules):
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
            # One source total cannot be assigned to every generated wall zone
            # or checkerboard product. Only retain it for a single application.
            shared_qty = qty if sum(1 for _, _, is_heading in generated if is_heading) <= 1 else ""
            page = records[heading].get("layout", {}).get("page")
            for text, row_qty, is_heading in generated:
                records.append({"room": context["room"], "type_description": text,
                                "selection_changed": "", "qty": shared_qty if row_qty is None else row_qty,
                                "layout": {"page": page, "is_heading": is_heading,
                                           "derived_from_change": True}})
        for index, item in all_candidates:
            used.add(index)
            if index in superseded:
                report[index].update(status="superseded", room=context["room"],
                                     application=context["application"],
                                     reason="Superseded by a later approved change order")
            else:
                report[index].update(status="applied", room=context["room"],
                                     application=context["application"],
                                     reason="Resolved matching See Change Order placeholder")
    return used


def apply_changes(records, instructions, rules=None):
    rules = rules_for(rules)
    sections = []
    for i, record in enumerate(records):
        if (not sections or record["room"] != records[sections[-1][0]]["room"]
                or record.get("layout", {}).get("is_heading")):
            sections.append([])
        sections[-1].append(i)
    report = [{**instruction, "status": "review", "application": application_kind(instruction["text"], rules) or "",
               "reason": "Unsupported or ambiguous instruction"} for instruction in instructions]
    used = resolve_placeholders(records, instructions, report, rules)
    for instruction_index, instruction in enumerate(instructions):
        entry = report[instruction_index]
        if instruction_index in used:
            continue
        action = re.match(r"(.+?)\s+-\s+(ADD|DELETE|REPLACE)\s+-\s+(.+)$", instruction["text"], re.I)
        if not action:
            if not entry.get("room"):
                entry.update(status="ignored",
                             reason="No See Change Order placeholder; current PDF rows retained")
            continue
        scope, operation, payload = action.groups()
        operation = operation.upper()
        eligible = [section for section in sections if scope_matches(
            scope, records[section[0]]["room"], records[section[0]]["type_description"], rules)]
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
                         application=application_kind(scope, rules) or application_kind(record["type_description"], rules) or "")
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
                     application=application_kind(scope, rules) or application_kind(records[matched[0]]["type_description"], rules) or "",
                     reason="Source section excluded" if operation == "DELETE" else "ADD already represented by source section")
    # A numbered placeholder can point to complementary ADD/DELETE instructions
    # that the legacy exact matcher applied directly to existing source sections.
    for context in placeholder_contexts(records, rules):
        if records[context["placeholder"]].get("excluded_by_change"):
            continue
        applied = [entry for entry in report if entry["status"] == "applied"
                   and entry.get("room") == context["room"]
                   and entry.get("application") == context["application"]
                   and (context["order_ref"] is None or entry["order"] == context["order_ref"])]
        if applied:
            records[context["placeholder"]]["excluded_by_change"] = "Resolved from approved change order"
    return report
