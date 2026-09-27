"""Command line: python -m pgx_translator QUEST_REPORT.pdf [-o OUTPUT_DIR]"""

from __future__ import annotations

import argparse
import sys

from .convert import FORMATS, convert
from .phenotypes import GREEN


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="pgx-translate",
        description="Convert a Quest Diagnostics pharmacogenomics PDF into Morpheus Precision Health reports.")
    ap.add_argument("reports", nargs="+", help="Quest PGx report PDF(s)")
    ap.add_argument("-o", "--out", default="morpheus_reports", help="output folder (default: %(default)s)")
    ap.add_argument("-f", "--formats", default=",".join(FORMATS),
                    help="comma list of: onepage, docx, pdf (default: all)")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't print the gene summary")
    args = ap.parse_args(argv)
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    bad = set(formats) - set(FORMATS)
    if bad:
        ap.error(f"unknown format(s): {', '.join(sorted(bad))}")

    status = 0
    for path in args.reports:
        try:
            out = convert(path, args.out, formats)
        except Exception as e:  # keep going with the other files
            print(f"ERROR {path}: {e}", file=sys.stderr)
            status = 1
            continue
        s = out.summary
        print(f"{path} -> {s.report.patient.display_name}")
        if not args.quiet:
            for g in s.genes_sorted:
                flag = "" if g.tier == GREEN else f"  [{g.tier.upper()}]"
                print(f"    {g.name:<12} {g.genotype:<22} {g.phenotype}{flag}")
        for f in out.files:
            print(f"    wrote {f}")
    return status


if __name__ == "__main__":
    sys.exit(main())
