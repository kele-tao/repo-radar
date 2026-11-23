"""One-off backfill: rewrite usage events for a month."""

import json
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: backfill.py <month>")
        return 2
    month = argv[1]
    payload = json.loads(sys.stdin.read() or "[]")
    kept = [row for row in payload if row.get("month") == month]
    print(json.dumps(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

# revision 16: Priya Raman

# revision 17: Jonas Weber
