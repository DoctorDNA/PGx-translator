# PGx Translator

Converts a **Quest Diagnostics Pharmacogenomics Panel** PDF into **Morpheus Precision Health** reports:

| Output | File |
| --- | --- |
| One-page medication summary (red / yellow / green) | `Morpheus_PGx_One_Page_<First>_<Last>.pdf` |
| Full Pharmacogenomics Report, editable | `Morpheus_PGx_Report_<First>_<Last>.docx` |
| Full Pharmacogenomics Report, print-ready | `Morpheus_PGx_Report_<First>_<Last>.pdf` |

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Windows quick start

1. Install Python from python.org (the Python install manager is fine). If it asks to add the
   commands directory to your PATH, answer **y**.
2. Put this folder wherever you like (for example `D:\PGx-translator`).
3. Double-click **Start Web Page.bat**, or drag a Quest PDF onto **Convert (drag PDF here).bat**.
   The first run installs the libraries it needs; reports are saved in `morpheus_reports`.

## Use

**Command line**

```bash
python3 -m pgx_translator "Quest_Report.pdf"                  # writes to ./morpheus_reports/
python3 -m pgx_translator report1.pdf report2.pdf -o out/     # several patients at once
python3 -m pgx_translator report.pdf -f onepage               # only the one-pager
```

It prints each gene result (flagged genes marked) and the files it wrote.

**Web page (local only)**

```bash
python3 -m pgx_translator.web
```

Open http://127.0.0.1:5000, upload the Quest PDF, and a zip with all three reports downloads.
Nothing is stored; the server only listens on your own machine.

## How it works

1. `quest_parser.py` reads the patient header and the *Test Results* table (gene, genotype, phenotype).
2. `phenotypes.py` normalizes each result (UM/RM/NM/IM/PM, decreased function, HLA positive, …) and
   computes CYP2D6/CYP2C9 activity scores from the diplotype.
3. `rules.py` is the **Morpheus PGx rules table**: one rule per drug (≈80 drugs) that returns the
   tier, the full-report sentence and the one-page short phrase. Sources are CPIC unless marked
   Literature / FDA label / DPWG.
4. `summary.py` groups drugs into the one-page cards; `onepage.py`, `full_pdf.py` and `full_docx.py` draw
   the reports. The one-pager shrinks its type automatically so it always fits on one page.

### Full report layout (v1.1)

- Each medication is a vertical card: name and status (Avoid or change / Adjust or monitor / Standard
  dosing), the recommendation on its own full-width line, then gene(s) and source.
- Drug names in the Gene Results "Key drugs affected" column are clickable links that jump to that drug's
  card in "All Medications" (PDF in any viewer; Word with Ctrl+click). Link labels come from
  `GENE_KEY_DRUGS` in `rules.py`; group words map to drugs in `report_text.py` (`_GROUP_TARGET`,
  `_GROUP_EXPAND`).
- Larger type throughout. The one-page summary is unchanged.

### Editing recommendations

All clinical wording and tier logic lives in `pgx_translator/rules.py`. Each drug is a small function,
for example:

```python
def efavirenz(gt):
    c = gt.code("CYP2B6")
    if c == "IM":
        return Rec(YELLOW, "Consider starting at 400 mg/day instead of 600 mg.",   # full report
                   "Consider 400 instead of 600 mg/day.")                         # one-pager
    ...
```

After changing rules, bump `RULES_VERSION` / `RULES_REVIEWED` (printed in the report's interpretation
notes) and run the tests:

```bash
python3 -m pip install pytest && python3 -m pytest
```

Tests use a de-identified sample (`tests/fixtures/quest_sample.txt`). Never commit real reports;
`.gitignore` excludes PDFs and DOCX files.

## Limitations

- Built for the Quest PGx panel layout (21 genes). Other labs' PDFs need a new parser.
- Phenotypes are taken as reported by the lab. Only tested alleles are considered.
- This is clinical decision support. Review the rules table against current CPIC guidance
  (cpicpgx.org/guidelines) before relying on it.

Fonts: DejaVu Sans (Bitstream Vera license) and Carlito (SIL OFL 1.1), bundled in `pgx_translator/assets/fonts`.
