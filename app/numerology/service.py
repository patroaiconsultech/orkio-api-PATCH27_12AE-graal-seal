from __future__ import annotations
import re

_ALPHA = {c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1)}

def _reduce_number(n: int) -> int:
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(abs(n)))
    return n

def name_number(full_name: str) -> int:
    total = 0
    for ch in re.sub(r"[^A-Za-z]", "", (full_name or "").upper()):
        total += _ALPHA.get(ch, 0)
    return _reduce_number(total or 1)

def life_path(birth_date: str) -> int:
    digits = [int(ch) for ch in birth_date if ch.isdigit()]
    return _reduce_number(sum(digits) or 1)
