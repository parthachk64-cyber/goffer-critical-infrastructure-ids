# Paper map

Source: *AI-Enhanced Cyber Threat Detection and Response Advancing National Security in Critical Infrastructure*,
Journal of Posthumanism 5(3), 2025, pp. 1667-1689, [doi:10.63332/joph.v5i3.965](https://doi.org/10.63332/joph.v5i3.965),
[publisher page](https://posthumanism.co.uk/jp/article/view/965) (CC BY-NC-ND 4.0). Page numbers are the journal's printed pages.
This repository is an **independent research companion**. It is not the authors' code, and none exists in the
sources checked (see "Supplements, data and code").

Evidence labels used everywhere: **paper reports** (stated in the article) · **companion implementation** (a choice made here) ·
**measured in this run** (produced by a script in this repository) · **unavailable in source** (the article does not give it).

## What the experimental sections actually say

Read in full (pp. 1682-1684). The Methodology, Data Collection and AI Model Training and Testing sections state that the study used
case studies, "publicly available cybersecurity information sets" and expert interviews, and "supervised and unsupervised machine
learning algorithms, which include neural networks with decision trees and anomaly detection models". The abstract (p. 1667) says
IDS were tested "through the accuracy and precision & recall method". The Results & Discussion section (p. 1683) is qualitative.

| Detail | Status |
|---|---|
| Named experimental dataset | unavailable in source |
| Train/test split, sample counts | unavailable in source |
| Model hyperparameters, trained weights | unavailable in source |
| Any accuracy, precision, recall or F1 value | unavailable in source (the Results section reports none) |
| Interview count, participants, transcripts | unavailable in source |
| Funding and data-availability statements | unavailable in source (also absent on the publisher page) |

Consequence: nothing in this repository reproduces a number from the paper, because the paper reports none.

## Substantive claims

| # | Claim (paraphrased) | Locator | Label | Where handled |
|---|---|---|---|---|
| C1 | AI improves threat detection and response for critical infrastructure | Abstract p.1667; Results p.1683 | paper reports; no quantitative support | Evaluated only on a public flow benchmark (`docs/results.md`); the deployment claim is out of reach |
| C2 | Combined qualitative and quantitative method: framework review, case studies, IDS tests, expert interviews | Abstract p.1667; Methodology p.1682 | paper reports; interviews unavailable in source | Case table `data/cases.csv`; IDS comparison in `src/infra_ids`; no interview data used or simulated |
| C3 | Supervised and unsupervised models, "neural networks with decision trees and anomaly detection" | AI Model Training and Testing p.1683 | paper reports | decision tree, Isolation Forest, MLP: `detectors.py` (companion implementation) |
| C4 | Decision trees and SVMs suit anomaly and pattern recognition; deep CNN/RNN models do best on complex threats but are costly | Comparative Analysis pp.1683-1684 | paper reports; no data shown | SVM, CNN and RNN are **not implemented** (see below) |
| C5 | Hybrid AI plus rule-based systems with human expertise cut false alarms | Comparative Analysis p.1684 | paper reports | `hybrid_iso_rule` and the rule-effect table in each report (measured in this run) |
| C6 | AI needs continual updating against new threats | Results p.1683 | paper reports | not tested: no temporal or drift data |
| C7 | Adversarial AI, data privacy and regulation limit adoption | Challenges p.1683 | paper reports | documentation only; privacy handled by design (no payloads, opaque IDs) |
| C8 | SOCs using AI give faster discovery and fewer human errors | Results p.1683; SOC section p.1679 | paper reports; unavailable in source | needs deployment logs; **not evaluated** |
| C9 | Policy and international-collaboration recommendations | pp.1684-1685 | paper reports | out of scope |

### SVM, CNN and RNN

The paper discusses them (p.1683) without any experiment. Not implemented: an SVM on 175k flow records with RBF kernels is costly and
adds no research question the MLP and tree do not already cover; the UNSW-NB15 partition files are independent flow rows with no
defensible sequence boundary, so a CNN or RNN over them would be a model of row order rather than of traffic. Revisit only with
per-host ordered sequences and a stated question.

## Figures

| Figure | Page | What it shows | What it supports | Companion handling |
|---|---|---|---|---|
| 1 | 1669 | Pie of threat vs AI-adoption levels (six categories, percentages) | Descriptive only; no data source, sample or year is given (unavailable in source) | none; not used as evidence |
| 2 | 1670 | "Counterattacking Cyber Threats: A Framework" cycle diagram | A conceptual framework; nothing testable | original diagram in `docs/architecture.md` |
| 3 | 1672 | Eight automated security functions | A list of functions AI could automate; no performance data | maps loosely to the triage stage only |
| 4 | 1676 | "Increase in IoT-Based Cyber Threats (2015-2025 Projection)", reported IoT incidents | A rising count to 2023 (about 14,500), then a line that falls to zero at "2025*". The label says projection; the underlying data, source and the meaning of "*" are unavailable in source. A fall to zero is not a plausible forecast and may be a placeholder | none; projection label preserved, not used |
| (unnumbered) | 1678 | "AI-Powered Cybercrime Incidents" 2018-2025* | Same pattern: rise to 2024 (about 1,200), then zero at 2025* | none |

## Tables

All seven are descriptive tick-matrices or scenario lists. They record which attributes an incident has, as judged by the authors, not
model observations. See `data/cases.csv` for sector-by-sector independent verification.

| Table | Page | Subject | Companion handling |
|---|---|---|---|
| 1 | 1673 | Energy: Colonial Pipeline, Ukraine grid, Triton, BlackEnergy | `cases.csv` rows 1-4; several ticks (for example AI-enhanced malware for Triton) are not supported by sources read |
| 2 | 1674 | Finance: UAE deepfake fraud, market manipulation, AI phishing, AI botnets | `cases.csv`; only the UAE case names an incident |
| 3 | 1675 | Government/defense: SolarWinds, Stuxnet, Chinese espionage, Russian disinformation | `cases.csv`; "AI-powered malware" for Stuxnet and SolarWinds is an author claim |
| 4 | 1675-1676 | Telecom/smart cities: Mirai, water hack, AI telecom fraud, IoT DDoS on 5G | `cases.csv` |
| 5 | 1677 | Nation-state incidents and impact | `cases.csv`; figures unchecked except SolarWinds incident existence |
| 6 | 1677 | Phishing/deepfake case studies | `cases.csv`; UK energy-firm case sourced, other two unverified |
| 7 | 1678-1679 | Cyberterrorism threat types, AI techniques, potential impact | scenario table; `cases.csv` marks it hypothetical |

## Observations about the article that a reader should know

These are factual observations from the printed PDF, not judgements of the authors' intent.

- Several citations as printed do not match the claim: Leffler (1990, *National security*) is cited for the EU NIS2 Directive (p.1671); Cardoni et al. (2022, seismic resilience of telecom networks) for Mirai (p.1675); Hemphill & Longstreet (2016, US retail data breaches) for the UAE deepfake fraud (p.1673).
- The submission declaration (p.1685) names the *International Journal of Information Management*, not the publishing journal.
- The ethics statement (p.1685) refers to approval "from the institution of the first author" with no identifier.
- Stuxnet (2010) is described as AI-powered (pp.1674-1675).

## Supplements, data and code

The publisher page lists the PDF only: no supplementary files, data-availability statement, code link or funding statement. The paper names no
dataset. Therefore: no author data or code was found, and none is reused. This repository's benchmark data is UNSW-NB15 (see `docs/data.md`),
chosen by this repository, not by the paper.

## Claims the benchmark can and cannot evaluate

| Can evaluate (on public flow records) | Cannot evaluate (needs other evidence) |
|---|---|
| Relative detection quality of tree, anomaly, MLP and rule models on one benchmark | Effect on national security or critical-infrastructure outcomes |
| Whether adding a rule to an anomaly detector changes precision/recall on the same records | SOC speed or analyst error reduction (needs deployment logs) |
| Inference wall-clock latency of a model on stated hardware | Interview findings, sector experience, regulation effects |
