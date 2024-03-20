"""Token based, deliberately bounded scalar A1 formula domain (not an Excel parser)."""

import re

from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import TokenizerError
from openpyxl.utils.cell import range_boundaries

SUPPORTED = frozenset(
    "SUM AVERAGE MIN MAX ABS ROUND ROUNDUP ROUNDDOWN IF IFERROR AND OR NOT SUMIF SUMIFS COUNT COUNTA COUNTIF COUNTIFS VLOOKUP INDEX MATCH DATE YEAR MONTH DAY EOMONTH SUMPRODUCT TODAY".split()
)
# TODAY is rejected as volatile below despite engine support.
VOLATILE = {"TODAY", "NOW", "RAND", "RANDBETWEEN", "OFFSET", "INDIRECT"}
CELL_RANGE = re.compile(r"^\$?[A-Z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Z]{1,3}\$?[1-9][0-9]*)?$")


def analyze(formula: str, sheets: list[str] | None = None) -> dict:
    result = {"errors": [], "warnings": [], "references": [], "functions": [], "unsupported": []}
    if not formula.startswith("=") or len(formula) > 2000:
        result["errors"].append("Formula must start with = and be at most 2000 characters")
        return result
    if any(c in formula for c in ("[", "]", "|", "{", "}", "\n", "\r")):
        result["errors"].append(
            "External/structured references, arrays, DDE and control characters are blocked"
        )
        return result
    try:
        tokens = Tokenizer(formula).items
    except (TokenizerError, IndexError, ValueError) as exc:
        result["errors"].append(f"Tokenizer: {exc}")
        return result
    depth = 0
    for token in tokens:
        if token.type in {"FUNC", "PAREN"}:
            depth += 1 if token.subtype == "OPEN" else -1
            if depth < 0:
                result["errors"].append("Unbalanced parentheses")
        if token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].upper()
            result["functions"].append(name)
            if name not in SUPPORTED or name in VOLATILE:
                result["unsupported"].append(name)
        if token.type == "OPERAND" and token.subtype == "NUMBER":
            result["warnings"].append(f"Literal {token.value}: verify it is an intended constant")
        if token.type == "OPERAND" and token.subtype == "ERROR":
            result["warnings"].append(f"Explicit error value: {token.value}")
        if token.type == "OPERAND" and token.subtype == "RANGE":
            ref = token.value
            result["references"].append(ref)
            parts = ref.rsplit("!", 1)
            coord = parts[-1]
            if len(parts) == 2 and sheets is not None:
                sheet = parts[0].strip("'").replace("''", "'")
                if sheet not in sheets:
                    result["errors"].append(f"Missing sheet: {sheet}")
            if not CELL_RANGE.fullmatch(coord):
                result["errors"].append(f"Only bounded A1 cell/range references supported: {ref}")
            else:
                left, top, right, bottom = range_boundaries(coord.replace("$", ""))
                if (
                    right > 16384
                    or bottom > 1048576
                    or (right - left + 1) * (bottom - top + 1) > 20000
                ):
                    result["errors"].append(f"Reference exceeds supported limits: {ref}")
    if depth:
        result["errors"].append("Unbalanced parentheses")
    if not tokens:
        result["errors"].append("Empty formula")
    if not result["references"]:
        result["warnings"].append("No cell references: possible hardcoded answer")
    if result["references"] and not any("$" in r for r in result["references"]):
        result["warnings"].append("Only relative references; check copy/fill behavior")
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result
