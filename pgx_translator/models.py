"""Data structures shared by the parser, the rules engine and the renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Patient:
    last_name: str = ""
    first_name: str = ""
    suffix: str = ""  # credential or generational suffix, e.g. "DO", "JR"
    dob: Optional[date] = None
    sex: str = ""  # "Male" / "Female" / ""

    @property
    def display_name(self) -> str:
        """'Jeff Reid, DO' style name used in the full report."""
        name = " ".join(p for p in (_title(self.first_name), _title(self.last_name)) if p)
        return f"{name}, {self.suffix}" if self.suffix else name

    @property
    def file_stub(self) -> str:
        parts = [_title(self.first_name), _title(self.last_name)]
        return "_".join(p.replace(" ", "_") for p in parts if p) or "Patient"


def _title(s: str) -> str:
    # Title-case while keeping hyphenated / apostrophe names sensible (O'Neil, Smith-Jones).
    out = []
    for word in s.split():
        out.append("-".join(
            "'".join(piece[:1].upper() + piece[1:].lower() for piece in part.split("'"))
            for part in word.split("-")
        ))
    return " ".join(out)


@dataclass
class GeneResult:
    gene: str
    genotype: str  # as printed by the lab, e.g. "*1/*7", "c.421C>A (C/C)", "Neg/Neg"
    phenotype: str  # as printed by the lab, e.g. "Intermediate Metabolizer"
    alleles_tested: str = ""


@dataclass
class LabReport:
    patient: Patient
    genes: dict[str, GeneResult] = field(default_factory=dict)
    lab: str = "Quest Diagnostics"
    test_name: str = ""
    specimen: str = ""
    collected: Optional[date] = None
    received: Optional[date] = None
    reported: Optional[date] = None
    reporting_id: str = ""
    cls_url: str = ""
