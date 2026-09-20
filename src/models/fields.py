"""Pure helpers over the hierarchical field schema (v2).

This module is the single runtime interface between the schema tree and the
extraction / merge / scoring code. Everything here is pure (no I/O, no torch)
so it stays unit-testable without a GPU.

Path conventions
----------------
- schema-level leaf path:  "page_1_basic_info.general_details.candidate_name"
  (array items are NOT indexed — one spec per item field)
- value-level leaf path:   "page_4_declarations.part_one[0].answer"
  (array instances ARE indexed; used by merge / provenance / per-row scoring)
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.models.schemas import FieldDefinition, SchemaConfig

Leaf = Tuple[str, FieldDefinition]


# ---------------------------------------------------------------- tree walks

def iter_leaves(specs: List[FieldDefinition],
                prefix: str = "") -> List[Leaf]:
    """All (schema-level dotted path, leaf spec) pairs, declaration order."""
    out: List[Leaf] = []
    for spec in specs:
        base = f"{prefix}{spec.field_name}"
        if spec.data_type == "object" and spec.children:
            out.extend(iter_leaves(spec.children, f"{base}."))
        elif spec.data_type == "array" and spec.item:
            if spec.item.data_type in ("object", "array"):
                # item is a container: its field_name is nominal, children
                # attach directly to the array path (e.g. 'part_one.answer')
                out.extend(iter_leaves(
                    spec.item.children or [spec.item], f"{base}."))
            else:
                # scalar item: the row itself is the leaf
                out.append((base, spec.item))
        else:
            out.append((base, spec))
    return out


def leaf_specs(schema: SchemaConfig) -> Dict[str, FieldDefinition]:
    """{schema-level leaf path: leaf spec} — for validation & scoring."""
    return {path: spec for path, spec in iter_leaves(schema.fields)}


# ---------------------------------------------------------------- null shapes

def _node_null(spec: FieldDefinition) -> Any:
    if spec.data_type == "object" and spec.children:
        return null_shape(spec.children)
    if spec.data_type == "array" and spec.item:
        if (spec.item.data_type in ("object", "array") and spec.template_rows):
            keys = {c.field_name: None for c in spec.item.children or []}
            return [{k: (base or {}).get(k) for k in keys}
                    for base in spec.template_rows]
        return []
    return None


def null_shape(specs: List[FieldDefinition]) -> dict:
    """Nested skeleton: every leaf null; arrays prefilled from template_rows.
    Used for GT templates and as the parse-failure fallback."""
    return {s.field_name: _node_null(s) for s in specs}


def prompt_skeleton(specs: List[FieldDefinition]) -> dict:
    """Like null_shape, but arrays show ONE null item row (prompt template)."""
    out: dict = {}
    for spec in specs:
        if spec.data_type == "object" and spec.children:
            out[spec.field_name] = prompt_skeleton(spec.children)
        elif spec.data_type == "array" and spec.item:
            item = prompt_skeleton([spec.item])
            out[spec.field_name] = [item[spec.item.field_name]]
        else:
            out[spec.field_name] = None
    return out


# ---------------------------------------------------------------- shaping

_NULL_LITERALS = {"null", "none", "n/a", "n.a."}


def _coerce_leaf(value: Any) -> Optional[str]:
    """Leaf value -> str|None (record contract: leaves are strings or null).
    Literal null-ish strings the model emits for empty cells ("null", "None",
    "N/A", "N.a.") are coerced to null — they are not transcribed values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).strip()
    if not s or s.lower() in _NULL_LITERALS:
        return None
    return s


def prune_node(node: Any, spec: FieldDefinition) -> Any:
    """Coerce arbitrary model JSON into the schema shape for one node."""
    if spec.data_type == "object" and spec.children:
        if not isinstance(node, dict):
            return null_shape(spec.children)
        return {c.field_name: prune_node(node.get(c.field_name), c)
                for c in spec.children}
    if spec.data_type == "array" and spec.item:
        if not isinstance(node, list):
            return []
        if spec.item.data_type in ("object", "array"):
            return [prune_node(row, spec.item) for row in node
                    if isinstance(row, dict)]
        return [_coerce_leaf(row) for row in node]
    return _coerce_leaf(node)


def prune_to_shape(obj: Any, specs: List[FieldDefinition]) -> dict:
    """Whole-document shaping: drop unknown keys, keep schema shape exactly."""
    if not isinstance(obj, dict):
        return null_shape(specs)
    return {s.field_name: prune_node(obj.get(s.field_name), s) for s in specs}


# ---------------------------------------------------------------- flat view

def flatten_fields(node: Any, specs: List[FieldDefinition],
                   prefix: str = "") -> Dict[str, Optional[str]]:
    """Nested shaped dict -> {value-level dotted path: leaf value}.
    Array instances are indexed: 'part_one[0].answer'."""
    out: Dict[str, Optional[str]] = {}
    if not isinstance(node, dict):
        return out
    for spec in specs:
        base = f"{prefix}{spec.field_name}"
        val = node.get(spec.field_name)
        if spec.data_type == "object" and spec.children:
            child = val if isinstance(val, dict) else {}
            out.update(flatten_fields(child, spec.children, f"{base}."))
        elif spec.data_type == "array" and spec.item:
            rows = val if isinstance(val, list) else []
            if spec.item.data_type in ("object", "array"):
                for i, row in enumerate(rows):
                    item = row if isinstance(row, dict) else {}
                    out.update(flatten_fields(item, spec.item.children
                                              or [spec.item],
                                              f"{base}[{i}]."))
            else:
                for i, row in enumerate(rows):
                    out[f"{base}[{i}]"] = _coerce_leaf(row)
        else:
            out[base] = _coerce_leaf(val)
    return out


def unflatten_fields(leaves: Dict[str, Any],
                     specs: List[FieldDefinition]) -> dict:
    """Inverse of flatten_fields: rebuild the nested shape (unknowns dropped)."""
    out: dict = {}
    for spec in specs:
        base = spec.field_name
        if spec.data_type == "object" and spec.children:
            inner = {k[len(base) + 1:]: v for k, v in leaves.items()
                     if k.startswith(base + ".")}
            out[base] = unflatten_fields(inner, spec.children)
        elif spec.data_type == "array" and spec.item:
            if spec.item.data_type in ("object", "array"):
                rows: Dict[int, Dict[str, Any]] = {}
                pat = re.compile(rf"^{re.escape(base)}\[(\d+)\]\.(.+)$")
                for k, v in leaves.items():
                    m = pat.match(k)
                    if m:
                        rows.setdefault(int(m.group(1)), {})[m.group(2)] = v
                out[base] = [unflatten_fields(rows[i],
                                              spec.item.children or [spec.item])
                             for i in sorted(rows)]
            else:
                rows = {}
                pat = re.compile(rf"^{re.escape(base)}\[(\d+)\]$")
                for k, v in leaves.items():
                    m = pat.match(k)
                    if m:
                        rows[int(m.group(1))] = v
                out[base] = [rows[i] for i in sorted(rows)]
        else:
            out[base] = leaves.get(base)
    return out


def count_non_null(node: dict, specs: List[FieldDefinition]) -> int:
    """Number of non-null leaves (for run logs)."""
    return sum(v is not None
               for v in flatten_fields(node, specs).values())


def skeleton_json(specs: List[FieldDefinition], indent: int = 2) -> str:
    return json.dumps(prompt_skeleton(specs), indent=indent)
