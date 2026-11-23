"""Leftover export helper. Nothing imports this module any more."""

from __future__ import annotations

import csv


def export_rows(path, rows) -> int:
    """Write rows to a CSV file and return the count."""
    handle = open(path, "w", encoding="utf-8")
    writer = csv.writer(handle)
    for row in rows:
        writer.writerow(row)
    handle.close()
    return len(rows)

# revision 32: Mira Chen

# revision 33: Tomas Oliveira
