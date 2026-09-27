"""Top-level conversion: Quest PDF -> Morpheus one-page PDF + full report (DOCX and PDF)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .full_docx import render_full_docx
from .full_pdf import render_full_pdf
from .onepage import render_one_page
from .quest_parser import parse_pdf
from .summary import Summary, build_summary

FORMATS = ("onepage", "docx", "pdf")


@dataclass
class Outputs:
    summary: Summary
    files: list[Path]


def convert(quest_pdf: str | Path, out_dir: str | Path = ".", formats=FORMATS) -> Outputs:
    report = parse_pdf(quest_pdf)
    summary = build_summary(report)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stub = report.patient.file_stub
    files = []
    if "onepage" in formats:
        files.append(render_one_page(summary, out_dir / f"Morpheus_PGx_One_Page_{stub}.pdf"))
    if "docx" in formats:
        files.append(render_full_docx(summary, out_dir / f"Morpheus_PGx_Report_{stub}.docx"))
    if "pdf" in formats:
        files.append(render_full_pdf(summary, out_dir / f"Morpheus_PGx_Report_{stub}.pdf"))
    return Outputs(summary, files)
