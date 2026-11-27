# Reference documents

Copies of Dominion Energy South Carolina documents the library's billing rules are based on. They are kept here,
rather than linked, because Dominion replaces the files at its URLs when a document is revised, and these are the
versions the code and docs cite.

| File | Document | Source | Used for |
| --- | --- | --- | --- |
| [`general-terms-and-conditions-gas.pdf`](general-terms-and-conditions-gas.pdf) | *Gas General Terms and Conditions*, effective on and after the first billing cycle of October 2023 (PSC Order No. 2023-737(A), Docket No. 2023-70-G) | [dominionenergy.com](https://www.dominionenergy.com/-/media/content/rates-and-tariffs/pdfs/south-carolina/natural-gas/other/general-terms-and-conditions-gas.pdf), copied 2026-11-27 | Definitions of billing month (28 to 34 days between meter reads, section I.B), therm, CCF and BTU (section II); cubic feet to therms conversion by each cycle's average heat content (section III.B); estimated bills (section IV.A). See `DEFAULT_THERMS_PER_CCF` and `docs/PRICING_API_PLAN.md` Q1. |

When a document is revised, add the new copy alongside the old one with its effective date in the file name, and
update the citations, so the reasoning behind past decisions stays checkable.
