# CPIC review log

Each rule in `pgx_translator/rules.py` is checked against the published CPIC guideline PDF.
A checked drug shows the guideline year in its source (e.g. "CPIC 2019") on every report;
"CPIC" alone means the rule is based on CPIC guidance but has not been checked yet.

## Checked

| Guideline (file reviewed) | Drugs | Result | Checked |
|---|---|---|---|
| CYP2D6/CYP2C19 & tricyclic antidepressants, 2016 update (CPT 2017;102:37), Tables 2–4 | amitriptyline, clomipramine, doxepin, imipramine, trimipramine, nortriptyline, desipramine | Tiers matched. Added: 50% start reduction if a TCA is warranted in CYP2D6 PM (and CYP2C19 PM tertiary amines); higher target dose with TDM in CYP2D6 UM; TDM for tertiary amines in CYP2C19 UM/RM; note that recommendations apply to depression-range doses (no change for IM/PM at low neuropathic-pain doses). | 2026-10-14 |
| CYP2D6 & atomoxetine, 2019, Table 3 (adults) | atomoxetine | **Changed.** Activity score 1.0 without CYP2D6\*10 (e.g. \*1/\*5) is dosed like normal metabolizers → green. AS 0.25–0.5, or 1.0 with \*10, and PM → slow schedule (40 mg/day, 80 mg/day only after 2 weeks) → yellow; previously these got the 3-day titration. Pediatric weight-based dosing (Table 2) referenced, not implemented. | 2026-10-14 |
| UGT1A1 & atazanavir, 2015, Table 2 | atazanavir | Tiers matched. Added CPIC discontinuation figures and counseling wording. | 2026-10-14 |
| HLA-B & abacavir, 2014 update | abacavir | Update states the 2012 original remains current; rule matches the 2012 recommendation. Original 2012 table not yet reviewed directly. | 2026-10-14 |
| HLA-B & allopurinol, 2015 update | allopurinol | Update states the 2013 original remains current; rule matches the 2013 recommendation. Original 2013 table not yet reviewed directly. | 2026-10-14 |
| TPMT/NUDT15 & thiopurines, **2025 update**, Tables 2–4 | azathioprine, mercaptopurine, thioguanine | **Changed.** Now drug-specific. New CPIC category: TPMT/NUDT15 compound intermediate → start 20–50% of standard dose (previously 30–80%). Single IM: 30–80% for all three drugs (thioguanine was 50–80% under the 2018 guideline). Any poor metabolizer: azathioprine → nonthiopurine alternative; mercaptopurine/thioguanine (malignancy) → 10-fold reduction, 3×/week; mercaptopurine nonmalignancy → alternative. | 2026-10-14 |
| HLA-A/HLA-B & carbamazepine/oxcarbazepine, 2017 update, Tables 2–3 | carbamazepine, oxcarbazepine | Tiers matched. Added: HLA-A\*31:01 positive with no alternative → use with closer monitoring, stop at first skin reaction; >3 months' prior tolerance → cautiously consider continued use; caution with other aromatic anticonvulsants when HLA-B\*15:02 positive. | 2026-10-14 |
| CYP2C19 & clopidogrel, 2022 update, Tables 2–3 | clopidogrel | Tiers matched. **Safety wording fixed:** the program previously suggested prasugrel for neurovascular indications; CPIC notes prasugrel is contraindicated after stroke/TIA (ticagrelor suggested instead). Split IM (avoid 75 mg for ACS/PCI; no recommendation for other CV indications) from PM (avoid clopidogrel if possible). | 2026-10-14 |
| CYP2D6 & opioids, 2021, Tables 2–4 | codeine, tramadol, hydrocodone; oxycodone, morphine, hydromorphone, fentanyl | Tiers matched. Codeine alternatives now "non-tramadol opioid" and tramadol "non-codeine opioid" as in CPIC; CYP2D6 indeterminate → no recommendation; hydrocodone UM → no recommendation. Oxycodone/morphine/hydromorphone/fentanyl: CPIC reviewed, no CYP2D6 recommendation. | 2026-10-14 |
| CFTR & ivacaftor | — | Not applicable: CFTR is not on the Quest panel and ivacaftor is not in the program. | 2026-10-14 |
| CYP2B6 & efavirenz, 2019, Table 2 | efavirenz | Tiers and doses matched (IM 400 mg; PM 400 or 200 mg; others 600 mg). Added CPIC notes on drug-level monitoring and pill burden. Applies to adults and children ≥40 kg. | 2026-10-14 |
| DPYD & fluoropyrimidines, 2017 update, Table 2 | fluorouracil, capecitabine, tegafur | **Changed.** Activity score 1.5 now "reduce by 25% to 50%" (was 50%); AS 1.0 stays 50%. AS 0.5: avoid, or <25% dose with early drug monitoring if no alternative; AS 0: avoid (the strongly-reduced-dose option no longer offered). Added CPIC's titration guidance; tegafur flagged as limited evidence. | 2026-10-14 |
| G6PD (expanded), 2023, Table 2 | dapsone | G6PD is not on the Quest panel. Dapsone's NAT2 rule (Literature) is unchanged, but its text now notes CPIC rates dapsone high risk in G6PD deficiency and to confirm G6PD status. | 2026-10-14 |
| RYR1/CACNA1S & volatile anesthetics/succinylcholine, 2019 | — | Not applicable: genes not on the Quest panel; drugs not in the program. | 2026-10-14 |
| MT-RNR1 & aminoglycosides (gentamicin) | — | Not applicable: gene not on the Quest panel; drug not in the program. | 2026-10-14 |

## Not yet checked

PPIs, voriconazole (CYP2C19); SSRIs/SNRIs (CYP2D6, CYP2C19, CYP2B6); ondansetron/tropisetron;
tamoxifen; beta-blockers (metoprolol); statins (SLCO1B1, ABCG2, CYP2C9); warfarin; NSAIDs; phenytoin;
tacrolimus; hydralazine (NAT2).

Non-CPIC rules (Literature / FDA label / DPWG): procainamide, isoniazid, dapsone, sulfasalazine,
amifampridine, methadone, midazolam, irinotecan, estrogen-containing therapy.
