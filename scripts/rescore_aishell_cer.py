"""Rescore an AISHELL report while ignoring script and numeral variants."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
import warnings
from pathlib import Path

import cn2an
from evaluate_aishell_cer import edit_distance
from opencc import OpenCC

_MIXED_UNIT = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)([十百千万亿])(?![十百千万亿])")
_UNIT_VALUE = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}


def normalize_equivalent(text: str, converter: OpenCC) -> str:
    """Canonicalize traditional characters and written/Arabic numerals."""
    simplified = converter.convert(unicodedata.normalize("NFKC", text).upper())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        numeric = cn2an.transform(simplified, "cn2an")

    def expand_mixed_unit(match: re.Match[str]) -> str:
        number = float(match.group(1))
        value = number * _UNIT_VALUE[match.group(2)]
        return str(int(value)) if value.is_integer() else str(value)

    numeric = _MIXED_UNIT.sub(expand_mixed_unit, numeric)
    return "".join(
        character
        for character in numeric
        if not unicodedata.category(character).startswith(("P", "S", "Z", "C"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        help="Return exit code 1 when normalized CER is not below --threshold",
    )
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between zero and one")

    report = json.loads(args.report.read_text(encoding="utf-8"))
    converter = OpenCC("t2s")
    total_edits = 0
    total_reference_chars = 0
    for sample in report["samples"]:
        reference = normalize_equivalent(sample["reference"], converter)
        hypothesis = normalize_equivalent(sample["hypothesis"], converter)
        edits = edit_distance(reference, hypothesis)
        reference_chars = len(reference)
        sample["equivalent_reference"] = reference
        sample["equivalent_hypothesis"] = hypothesis
        sample["equivalent_edits"] = edits
        sample["equivalent_cer"] = edits / reference_chars
        total_edits += edits
        total_reference_chars += reference_chars

    normalized_cer = total_edits / total_reference_chars
    report["raw_cer"] = report.get("raw_cer", report["cer"])
    report["raw_passed"] = report.get("raw_passed", report["passed"])
    report["normalization"] = (
        "OpenCC traditional-to-simplified; cn2an written numerals-to-Arabic; "
        "Unicode NFKC; uppercase; remove punctuation, symbols, separators and controls"
    )
    report["total_edits"] = total_edits
    report["total_reference_chars"] = total_reference_chars
    report["cer"] = normalized_cer
    report["character_accuracy"] = 1 - normalized_cer
    report["threshold"] = args.threshold
    report["passed"] = normalized_cer < args.threshold

    temporary = args.report.with_suffix(args.report.suffix + ".writing")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(args.report)
    print(
        json.dumps(
            {
                "sample_count": report["sample_count"],
                "raw_cer": report["raw_cer"],
                "normalized_cer": normalized_cer,
                "character_accuracy": 1 - normalized_cer,
                "threshold": args.threshold,
                "passed": report["passed"],
                "report": str(args.report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if args.fail_on_threshold and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
