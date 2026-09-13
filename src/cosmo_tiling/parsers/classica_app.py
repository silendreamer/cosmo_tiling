"""Adapt the shared Classica column parser to app workbook rows."""
from collections import OrderedDict

from .classica_columns import (
    APPLICATION_ALIASES, LABEL_ALIASES, application_kind, extract, field,
    normalized, product_fields, table_rows,
)
from .common import OrderRow

REVIEW_TYPES = {"Unclassified (review)", "Review required"}
TYPE_NAMES = {"shower_wall": ("Shower wall", "Shower Wall"),
              "shower_floor": ("Shower Floor", "Shower Floor"),
              "floor": ("Floor Tile", "Floor Tile"),
              "backsplash": ("Backsplash", "Backsplash"),
              "surround": ("Wall Tile", "Wall Tile"), "wall": ("Wall Tile", "Wall Tile")}


def build_classica_document(path, template, *, apply_revisions=True):
    document = extract(path, apply_revisions=apply_revisions)
    applications = {**APPLICATION_ALIASES, **{
        normalized(k): v for k, v in template.get("application_aliases", {}).items()}}
    labels = {**LABEL_ALIASES, **{
        normalized(k): v for k, v in template.get("label_aliases", {}).items()}}
    rooms = OrderedDict()
    for raw in document["rows"]:
        rooms.setdefault(raw["room"], []).append(raw)
    rows = []
    for room, raw_rows in rooms.items():
        # Match rendered selections back to their original text and pattern.
        selections = {}
        pattern = ""
        for raw in raw_rows:
            if raw.get("excluded_by_change"):
                continue
            text = " ".join(raw["type_description"].split())
            if raw.get("layout", {}).get("is_heading") and application_kind(text, applications):
                pattern = ""
            if normalized(text).startswith("pattern:"):
                pattern = text.split(":", 1)[1].strip()
            if field(text, labels)[0] == "selection":
                selections.setdefault(product_fields(text, labels), []).append((raw, pattern))
        related = ""
        for item_type, size, description, quantity, unit in table_rows(raw_rows, applications, labels):
            canonical = application_kind(item_type, applications)
            pattern = ""
            source = description
            if canonical:
                display, related = TYPE_NAMES.get(canonical, (item_type, item_type))
            else:
                display = item_type
            matches = selections.get((size, description), [])
            if matches:
                raw, pattern = matches[0]
                source = f"{raw['type_description']} | Qty: {raw['qty']} | Changed: {raw['selection_changed']}"
            elif item_type in {"Caulk", "Drain riser plug", "Sealer"}:
                source = f"Derived accessory rule for {room}: {description}"
            else:
                candidates = [r for r in raw_rows if description and description in r["type_description"]]
                if candidates:
                    source = candidates[0]["type_description"]
            rows.append(OrderRow(room=room, item_type=display, size_area=size,
                                 description=description, order_qty=quantity if quantity != "" else None,
                                 unit=unit, pattern=pattern, source_text=source,
                                 related_type=related, comments="Requires review" if item_type in REVIEW_TYPES else ""))
    for change in document["change_report"]:
        if change["status"] == "review":
            rows.append(OrderRow(room=change.get("room", "Review"), item_type="Review required",
                                 description=change["text"], comments=change["reason"],
                                 source_text=f"Change Order #{change['order']}: {change['text']}"))
    if not any(row.item_type not in REVIEW_TYPES for row in rows):
        raise ValueError("No recognized tile-order selections were found in the PDF")
    return rows, document


def append_source_sheets(output_path, document, prefix=""):
    """Keep exact extracted values and revision decisions available for auditing."""
    from openpyxl import load_workbook
    workbook = load_workbook(output_path)
    source = workbook.create_sheet(prefix + "Source")
    source.append(["Room Code", "Type / Description", "Selection Changed", "Qty", "Page", "Excluded by change"])
    for raw in document["rows"]:
        values = [raw["room"], raw.get("original_description", raw["type_description"]),
                  raw["selection_changed"], raw["qty"], raw.get("layout", {}).get("page"),
                  raw.get("excluded_by_change", "")]
        source.append(values)
    source.freeze_panes = "A2"
    source.column_dimensions["B"].width = 100
    if document["change_report"]:
        report = workbook.create_sheet(prefix + "Change Review")
        report.append(["Change Order", "Status", "Room", "Instruction", "Reason"])
        for entry in document["change_report"]:
            report.append([entry["order"], entry["status"], entry.get("room", ""), entry["text"], entry["reason"]])
        report.column_dimensions["D"].width = 100
    # PDF content is audit text, including any leading equals signs.
    for sheet in workbook.worksheets:
        if sheet.title in {prefix + "Source", prefix + "Change Review"}:
            for cells in sheet.iter_rows():
                for cell in cells:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
    workbook.save(output_path)
    workbook.close()
