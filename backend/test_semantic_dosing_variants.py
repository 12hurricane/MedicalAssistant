import re
from app.analysis.response_validator import PROHIBITED_DOSING_PATTERNS

variants = [
    "Double your next dose.",
    "Take twice the amount next time.",
    "Increase your dose.",
    "Stop taking this medication.",
    "Discontinue the medication.",
    "Skip the next dose.",
    "Change your medication schedule.",
]

print("REGEX MATCHES:")
for variant in variants:
    matched = False
    for pattern in PROHIBITED_DOSING_PATTERNS:
        if re.search(pattern, variant.lower()):
            matched = True
            print(f"CAUGHT: {variant}")
            break
    if not matched:
        print(f"MISSED: {variant}")
