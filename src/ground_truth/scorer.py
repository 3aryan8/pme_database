"""GATE 1 harness: per-field accuracy, error taxonomy, typed-vs-handwritten.

Compares extractions against hand-typed ground truth:
  data/ground_truth/gt/{doc}.json          (development scoring)
  data/ground_truth/eval_holdout/{doc}.json (score sparingly: --include-holdout)

Taxonomy (per master roadmap):
  correct / wrong / missed / hallucinated / correctly_nulled
  ('?' in GT = unreadable, excluded from scoring)

Usage: uv run python -m src.ground_truth.scorer [--include-holdout] [--tag X]
"""
import argparse
import json
import sys
from pathlib import Path

from src.ground_truth.normalize import normalize_value
from src.models.schemas import GroundTruthDoc
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("eval")
GATE_THRESHOLD = 0.90


def _as_dict(node) -> dict:
    return node if isinstance(node, dict) else {}


def load_gt(gt_dir: Path) -> dict:
    docs = {}
    for p in sorted(gt_dir.glob("*.json")):
        gt = GroundTruthDoc(**json.loads(p.read_text()))
        docs[gt.document_id] = gt.fields
    return docs


def score_document(doc_id, gt_fields, ex_fields, schema) -> list:
    """Recursively score the nested GT/EX dicts against the schema tree.
    Array rows are scored positionally (row i vs row i); a missing row
    scores its leaves as null."""
    rows = []
    known = {s.field_name for s in schema.fields}
    for key in _as_dict(gt_fields):
        if key not in known:
            log.warning("GT key '%s' not in schema.yaml — fix one of them",
                        key)
    _score_node(doc_id, _as_dict(gt_fields), _as_dict(ex_fields),
                schema.fields, "", rows)
    return rows


def _score_leaf(doc_id, path, spec, gt_val, ex_val, rows) -> None:
    if gt_val == "?":
        return
    g = normalize_value(gt_val, spec.data_type, spec.field_name)
    e = normalize_value(ex_val, spec.data_type, spec.field_name)
    if g is None and e is None:
        tax = "correctly_nulled"
    elif g is None:
        tax = "hallucinated"
    elif e is None:
        tax = "missed"
    elif g == e:
        tax = "correct"
    else:
        tax = "wrong"
    rows.append({"doc": doc_id, "field": path,
                 "source_type": spec.source_type, "taxon": tax,
                 "gt": gt_val, "ex": ex_val})


def _score_node(doc_id, gt_node, ex_node, specs, prefix, rows) -> None:
    for spec in specs:
        path = f"{prefix}{spec.field_name}"
        if spec.data_type == "object" and spec.children:
            _score_node(doc_id,
                        _as_dict(gt_node.get(spec.field_name)),
                        _as_dict(ex_node.get(spec.field_name)),
                        spec.children, f"{path}.", rows)
        elif spec.data_type == "array" and spec.item:
            gt_rows = gt_node.get(spec.field_name)
            ex_rows = ex_node.get(spec.field_name)
            gt_rows = gt_rows if isinstance(gt_rows, list) else []
            ex_rows = ex_rows if isinstance(ex_rows, list) else []
            if spec.item.data_type in ("object", "array"):
                inner_specs = spec.item.children or [spec.item]
                for i in range(max(len(gt_rows), len(ex_rows))):
                    gt_row = gt_rows[i] if i < len(gt_rows) else None
                    ex_row = ex_rows[i] if i < len(ex_rows) else None
                    _score_node(doc_id, _as_dict(gt_row), _as_dict(ex_row),
                                inner_specs, f"{path}[{i}].", rows)
            else:
                for i in range(max(len(gt_rows), len(ex_rows))):
                    _score_leaf(doc_id, f"{path}[{i}]", spec.item,
                                gt_rows[i] if i < len(gt_rows) else None,
                                ex_rows[i] if i < len(ex_rows) else None, rows)
        else:
            _score_leaf(doc_id, path, spec,
                        gt_node.get(spec.field_name),
                        ex_node.get(spec.field_name), rows)


def _aggregate(rows, key_fn) -> list:
    groups: dict = {}
    for r in rows:
        k = key_fn(r)
        groups.setdefault(k, {"correct": 0, "wrong": 0, "missed": 0,
                               "hallucinated": 0, "correctly_nulled": 0})
        groups[k][r["taxon"]] += 1
    table = []
    for k in sorted(groups):
        c = groups[k]
        denom = c["correct"] + c["wrong"] + c["missed"]
        acc = c["correct"] / denom if denom else 0.0
        table.append((k, denom, c, acc))
    return table


def _fmt_table(title, table) -> str:
    lines = [f"\n{title}",
             f"{'key':<28}{'n':>5}{'corr':>6}{'wrong':>6}{'miss':>6}"
             f"{'hallu':>6}{'nulOK':>6}{'acc':>8}",
             "-" * 71]
    for k, denom, c, acc in table:
        lines.append(f"{str(k)[:27]:<28}{denom:>5}{c['correct']:>6}"
                     f"{c['wrong']:>6}{c['missed']:>6}{c['hallucinated']:>6}"
                     f"{c['correctly_nulled']:>6}{acc:>8.1%}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-holdout", action="store_true")
    ap.add_argument("--tag", type=str, default=None,
                    help="suffix for the report filename (A/B runs)")
    args = ap.parse_args()

    gt_root = config.root_dir / "data/ground_truth/gt"
    holdout_root = config.root_dir / "data/ground_truth/eval_holdout"
    ex_root = config.get_path("processed_dir") / "extractions"

    gt_docs = load_gt(gt_root)
    if args.include_holdout:
        gt_docs.update(load_gt(holdout_root))
    if not gt_docs:
        log.error("no ground truth in %s — run scripts/make_gt_template.py "
                  "and hand-type it first", gt_root)
        return 1

    rows, missing = [], []
    for doc, gt_fields in gt_docs.items():
        rec = ex_root / doc / "record.json"
        if not rec.exists():
            missing.append(doc)
            continue
        ex_fields = json.loads(rec.read_text())["fields"]
        rows.extend(score_document(doc, gt_fields, ex_fields, config.schema))
    if missing:
        log.warning("no extraction record for %d GT doc(s): %s",
                    len(missing), [d[:12] for d in missing])
    if not rows:
        log.error("nothing scored")
        return 1

    by_source = _aggregate(rows, lambda r: r["source_type"])
    by_field = _aggregate(rows, lambda r: r["field"])

    print(f"\nGATE 1 — {len(gt_docs)} docs, {len(rows)} scored field-values")
    print(_fmt_table("BY SOURCE TYPE (the Gate 1 split)", by_source))
    print(_fmt_table("BY FIELD", by_field))

    typed = next(((d, c, a) for k, d, c, a in by_source if k == "typed"), None)
    if typed:
        denom, counts, acc = typed
        verdict = "PASS" if acc >= GATE_THRESHOLD else "FAIL"
        print(f"\nGATE 1 (typed fields >= {GATE_THRESHOLD:.0%}): {verdict} "
              f"— {acc:.1%} over {denom} values")
        if denom < 20:
            print("  sample size < 20: treat as direction, not precision — "
                  "expand GT before concluding")
    else:
        print("\nno typed fields scored — check schema source_types")

    mism = [r for r in rows if r["taxon"] in ("wrong", "missed", "hallucinated")]
    print(f"\nMISMATCHES ({len(mism)}) — iterate the prompt/schema against these:")
    for r in mism[:30]:
        print(f"  {r['doc'][:10]} {r['field']:<46} [{r['taxon']}] "
              f"GT={r['gt']!r} EX={r['ex']!r}")

    stem = f"gate1_report{'_' + args.tag if args.tag else ''}"
    out_dir = config.get_path("processed_dir") / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stem}.json").write_text(json.dumps(rows, indent=2))
    print(f"\nreport written: {out_dir / (stem + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())