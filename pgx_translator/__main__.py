"""Command line: python -m pgx_translator QUEST_REPORT.pdf [-o OUTPUT_DIR]"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from .convert import FORMATS, convert
from .medications import drug_list_markdown, split_entries
from .phenotypes import GREEN


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="pgx-translate",
        description="Convert a Quest Diagnostics pharmacogenomics PDF into Morpheus Precision Health reports.")
    ap.add_argument("reports", nargs="*", help="Quest PGx report PDF(s)")
    ap.add_argument("-o", "--out", default="morpheus_reports", help="output folder (default: %(default)s)")
    ap.add_argument("-f", "--formats", default=",".join(FORMATS),
                    help="comma list of: onepage, docx, pdf (default: all)")
    ap.add_argument("-m", "--meds", default="",
                    help='patient medications, comma separated, e.g. "Lipitor 40 mg, sertraline"')
    ap.add_argument("--meds-file", help="text file with the patient's medications, one per line")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't print the gene summary")
    ap.add_argument("--list-drugs", action="store_true", help="print every medication the program recognizes")
    args = ap.parse_args(argv)
    if args.list_drugs:
        print(drug_list_markdown())
        return 0
    if not args.reports:
        ap.error("give at least one Quest report PDF")
    meds = split_entries(args.meds)
    if args.meds_file:
        meds += split_entries(Path(args.meds_file).read_text(encoding="utf-8", errors="replace"))
    if meds and len(args.reports) > 1:
        ap.error("--meds/--meds-file apply to one patient; convert one report at a time")
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    bad = set(formats) - set(FORMATS)
    if bad:
        ap.error(f"unknown format(s): {', '.join(sorted(bad))}")

    status = 0
    for path in args.reports:
        try:
            out = convert(path, args.out, formats, medications=meds)
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
        if s.patient_meds:
            print("    Patient medications:")
            for m in s.patient_meds:
                fuzzy = f"  (matched '{m.entered}' -> {m.name}; check spelling)" if m.fuzzy else ""
                print(f"      [{m.status}] {m.display_name}: {m.short}{fuzzy}")
        for f in out.files:
            print(f"    wrote {f}")
    return status


if __name__ == "__main__":
    sys.exit(main())
