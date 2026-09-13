"""Load and validate editable rules for the Classica PDF format."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from string import Formatter

DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "rules" / "classica-rules.json"
)


def merge_rules(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_rules(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _object(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"Classica rules {path} must be an object")
    return value


def _string_map(value, path):
    value = _object(value, path)
    if any(not isinstance(key, str) or not isinstance(item, str)
           for key, item in value.items()):
        raise ValueError(f"Classica rules {path} must map strings to strings")
    return value


def _string_list(value, path):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Classica rules {path} must be an array of strings")
    return value


def _regex(value, path):
    if not isinstance(value, str):
        raise ValueError(f"Classica rules {path} must be a string")
    try:
        re.compile(value)
    except re.error as error:
        raise ValueError(f"Classica rules {path} is not a valid regular expression: {error}") from error
    return value


def validate_classica_rules(rules: dict, source="Classica rules") -> dict:
    rules = _object(rules, source)
    if rules.get("schema_version") != 1:
        raise ValueError(f"{source}.schema_version must be 1")

    applications = _object(rules.get("applications"), f"{source}.applications")
    aliases = _string_map(applications.get("aliases"), f"{source}.applications.aliases")
    presentation = _object(
        applications.get("presentation"), f"{source}.applications.presentation"
    )
    categories = set(aliases.values())
    for category, values in presentation.items():
        values = _object(values, f"{source}.applications.presentation.{category}")
        if not isinstance(values.get("display"), str) or not isinstance(values.get("related"), str):
            raise ValueError(
                f"{source}.applications.presentation.{category} requires display and related strings"
            )
        if not isinstance(values.get("priority"), (int, float)):
            raise ValueError(
                f"{source}.applications.presentation.{category}.priority must be numeric"
            )
        if "preserve_source_type" in values and not isinstance(
                values["preserve_source_type"], bool):
            raise ValueError(
                f"{source}.applications.presentation.{category}.preserve_source_type must be boolean"
            )
    missing = categories - set(presentation)
    if missing:
        raise ValueError(f"{source}.applications.presentation is missing {sorted(missing)}")

    fields = _object(rules.get("fields"), f"{source}.fields")
    field_categories = set(_string_list(
        fields.get("categories"), f"{source}.fields.categories"))
    field_aliases = _string_map(fields.get("aliases"), f"{source}.fields.aliases")
    if set(field_aliases.values()) - field_categories:
        raise ValueError(f"{source}.fields.aliases contains an unsupported category")
    selection_patterns = _string_list(
        fields.get("selection_patterns"), f"{source}.fields.selection_patterns")
    for index, pattern in enumerate(selection_patterns):
        _regex(pattern, f"{source}.fields.selection_patterns[{index}]")
    for name in ("material_prefixes", "schluter_prefixes", "niche_prefixes",
                 "corner_shelf_prefixes", "supply_prefixes", "context_prefixes"):
        _string_list(fields.get(name), f"{source}.fields.{name}")

    units = _object(rules.get("units"), f"{source}.units")
    _string_list(units.get("accepted"), f"{source}.units.accepted")
    _string_map(units.get("normalize"), f"{source}.units.normalize")

    recognition = _object(rules.get("recognition"), f"{source}.recognition")
    for name in ("compact_summary_pattern", "thin_brick_pattern",
                 "thin_brick_detail_pattern", "generic_product_pattern",
                 "product_group_prefix_pattern", "stone_material_pattern"):
        _regex(recognition.get(name), f"{source}.recognition.{name}")
    _string_list(recognition.get("note_prefixes"), f"{source}.recognition.note_prefixes")
    _string_list(recognition.get("tub_room_phrases"),
                 f"{source}.recognition.tub_room_phrases")

    quantity = _object(rules.get("quantity"), f"{source}.quantity")
    formula = quantity.get("formula_template")
    comment = quantity.get("review_comment_template")
    if not isinstance(formula, str) or {
        field for _, field, _, _ in Formatter().parse(formula) if field
    } != {"measured", "waste"}:
        raise ValueError(
            f"{source}.quantity.formula_template must contain exactly {{measured}} and {{waste}}"
        )
    if not isinstance(comment, str) or {
        field for _, field, _, _ in Formatter().parse(comment) if field
    } - {"measured", "waste", "unit"}:
        raise ValueError(
            f"{source}.quantity.review_comment_template has unsupported placeholders"
        )
    rules_list = quantity.get("waste_rules")
    if not isinstance(rules_list, list) or not rules_list:
        raise ValueError(f"{source}.quantity.waste_rules must be a non-empty array")
    for index, rule in enumerate(rules_list):
        rule = _object(rule, f"{source}.quantity.waste_rules[{index}]")
        if not isinstance(rule.get("percent"), (int, float)) or rule["percent"] < 0:
            raise ValueError(
                f"{source}.quantity.waste_rules[{index}].percent must be non-negative"
            )
        for name in ("any_keywords",):
            if name in rule:
                _string_list(rule[name], f"{source}.quantity.waste_rules[{index}].{name}")
        if "applications" in rule:
            _string_list(rule["applications"],
                         f"{source}.quantity.waste_rules[{index}].applications")
            if set(rule["applications"]) - categories:
                raise ValueError(
                    f"{source}.quantity.waste_rules[{index}].applications contains "
                    "an unsupported category"
                )
        if "all_keyword_groups" in rule:
            groups = rule["all_keyword_groups"]
            if not isinstance(groups, list):
                raise ValueError(
                    f"{source}.quantity.waste_rules[{index}].all_keyword_groups must be an array"
                )
            for group_index, group in enumerate(groups):
                _string_list(
                    group,
                    f"{source}.quantity.waste_rules[{index}].all_keyword_groups[{group_index}]",
                )
        if "min_dimension" in rule and not isinstance(rule["min_dimension"], (int, float)):
            raise ValueError(
                f"{source}.quantity.waste_rules[{index}].min_dimension must be numeric"
            )

    accessories = _object(rules.get("accessories"), f"{source}.accessories")
    accessory_categories = set(_string_list(
        accessories.get("categories"), f"{source}.accessories.categories"))
    purchasable = set(_string_list(accessories.get("purchasable_categories"),
                                  f"{source}.accessories.purchasable_categories"))
    selection_only = set(_string_list(accessories.get("selection_only_categories"),
                                     f"{source}.accessories.selection_only_categories"))
    if (purchasable | selection_only) - accessory_categories:
        raise ValueError(f"{source}.accessories contains an unsupported category")
    order = _object(accessories.get("order"), f"{source}.accessories.order")
    if any(not isinstance(key, str) or not isinstance(value, (int, float))
           for key, value in order.items()):
        raise ValueError(f"{source}.accessories.order must map categories to numeric priorities")
    if set(order) - accessory_categories:
        raise ValueError(f"{source}.accessories.order contains an unsupported category")
    accessory_display = _string_map(accessories.get("display"),
                                    f"{source}.accessories.display")
    if set(accessory_display) - accessory_categories:
        raise ValueError(f"{source}.accessories.display contains an unsupported category")
    for name in ("drain_riser", "caulk", "sealer"):
        _object(accessories.get(name), f"{source}.accessories.{name}")

    changes = _object(rules.get("change_orders"), f"{source}.change_orders")
    change_categories = set(_string_list(
        changes.get("application_categories"),
        f"{source}.change_orders.application_categories"))
    for name in ("approved_headings", "stop_headings", "instruction_prefixes"):
        _string_list(changes.get(name), f"{source}.change_orders.{name}")
    change_phrases = _string_map(changes.get("application_phrases"),
                                 f"{source}.change_orders.application_phrases")
    if set(change_phrases.values()) - change_categories:
        raise ValueError(f"{source}.change_orders.application_phrases contains an unsupported category")
    _string_map(changes.get("zone_labels"), f"{source}.change_orders.zone_labels")
    aliases = changes.get("room_scope_aliases")
    if not isinstance(aliases, list):
        raise ValueError(f"{source}.change_orders.room_scope_aliases must be an array")
    for index, alias in enumerate(aliases):
        alias = _object(alias, f"{source}.change_orders.room_scope_aliases[{index}]")
        if not isinstance(alias.get("phrase"), str) or not isinstance(alias.get("room_pattern"), str):
            raise ValueError(
                f"{source}.change_orders.room_scope_aliases[{index}] requires phrase and room_pattern"
            )
        _regex(alias["room_pattern"],
               f"{source}.change_orders.room_scope_aliases[{index}].room_pattern")
    scope_patterns = changes.get("scope_patterns")
    if not isinstance(scope_patterns, list):
        raise ValueError(f"{source}.change_orders.scope_patterns must be an array")
    for index, item in enumerate(scope_patterns):
        item = _object(item, f"{source}.change_orders.scope_patterns[{index}]")
        if (not isinstance(item.get("scope_pattern"), str)
                or item.get("target") not in {"room", "heading"}
                or not isinstance(item.get("target_pattern"), str)):
            raise ValueError(
                f"{source}.change_orders.scope_patterns[{index}] requires scope_pattern, "
                "a room/heading target, and target_pattern"
            )
        _regex(item["scope_pattern"],
               f"{source}.change_orders.scope_patterns[{index}].scope_pattern")
        try:
            target_pattern = item["target_pattern"].format(*(["1"] * 10))
        except (IndexError, KeyError, ValueError) as error:
            raise ValueError(
                f"{source}.change_orders.scope_patterns[{index}].target_pattern has invalid placeholders"
            ) from error
        _regex(target_pattern,
               f"{source}.change_orders.scope_patterns[{index}].target_pattern")
    review = _object(rules.get("review"), f"{source}.review")
    _string_list(review.get("row_types"), f"{source}.review.row_types")
    for name in ("unclassified_type", "required_type", "required_comment", "metadata_label"):
        if not isinstance(review.get(name), str):
            raise ValueError(f"{source}.review.{name} must be a string")
    metadata_template = review.get("metadata_template")
    if not isinstance(metadata_template, str) or {
        field for _, field, _, _ in Formatter().parse(metadata_template) if field
    } != {"count"}:
        raise ValueError(f"{source}.review.metadata_template must contain exactly {{count}}")
    return rules


@lru_cache(maxsize=4)
def load_classica_rules(path: str | Path = DEFAULT_RULES_PATH) -> dict:
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Classica rules file not found: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid Classica rules JSON at {path}: {error}") from error
    return validate_classica_rules(data, str(path))


def rules_for(template: dict | None = None) -> dict:
    if template and template.get("schema_version") == 1 and "applications" in template:
        return template
    if template and "classica_rules" in template:
        return template["classica_rules"]
    return load_classica_rules()
