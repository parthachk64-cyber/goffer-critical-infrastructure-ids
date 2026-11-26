# Run report: 20261126T020840Z-s42

**Data label:** INDEPENDENT BENCHMARK: UNSW-NB15 official partitions

Positive class: label == 1 (attack). Seed 42. Model version `infra-ids-0.1.0-seed42`,
source revision `57958ae63948d699ffb866174d47a6a951235085`. Every number below is regenerated from `predictions.csv` and
`manifest.json` in this directory by `python -m infra_ids report --run <dir>`.

## Inputs

| partition | file | SHA-256 | rows | label 0 | label 1 |
|---|---|---|---|---|---|
| train | UNSW_NB15_training-set.csv | `bec7dd5ec88dc2a0...` | 175,341 | 56,000 | 119,341 |
| test | UNSW_NB15_testing-set.csv | `734fe6642edf758f...` | 82,332 | 37,000 | 45,332 |

Full hashes, ignored columns and the split are in `manifest.json`. Thresholds and preprocessing used the
fit/validation rows of the training file only (140,272 fit, 35,069 validation).

## Held-out results (all test rows, n=82,332, prevalence 0.5506)

| model | threshold | tp | fp | tn | fn | accuracy | precision | recall | f1 | fpr | average_precision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| majority_reference | 0.5000 | 45332 | 37000 | 0 | 0 | 0.5506 | 0.5506 | 1.0000 | 0.7102 | 1.0000 | n/a |
| rule_baseline | 0.5000 | 29727 | 6508 | 30492 | 15605 | 0.7314 | 0.8204 | 0.6558 | 0.7289 | 0.1759 | n/a |
| decision_tree | 0.4839 | 44130 | 11153 | 25847 | 1202 | 0.8499 | 0.7983 | 0.9735 | 0.8772 | 0.3014 | 0.9773 |
| isolation_forest | 0.7345 | 38456 | 13893 | 23107 | 6876 | 0.7477 | 0.7346 | 0.8483 | 0.7874 | 0.3755 | 0.8010 |
| mlp | 0.4874 | 44635 | 10089 | 26911 | 697 | 0.8690 | 0.8156 | 0.9846 | 0.8922 | 0.2727 | 0.9849 |
| hybrid_iso_rule | 0.7317 | 38559 | 14196 | 22804 | 6773 | 0.7453 | 0.7309 | 0.8506 | 0.7862 | 0.3837 | 0.8155 |

Thresholds: maximise F1 on validation rows; ties to the higher threshold; reference models use 0.5 on a fixed score. `average_precision` is `n/a` for the majority and rule references
(constant or binary scores). Plots: `plots/confusion_matrices.png`, `plots/precision_recall.png`.

## Effect of adding the rule to the Isolation Forest (same records, same detector)

| | Isolation Forest | + rule (hybrid) |
|---|---|---|
| recall | 0.8483 | 0.8506 |
| precision | 0.7346 | 0.7309 |
| F1 | 0.7874 | 0.7862 |
| FPR | 0.3755 | 0.3837 |
| average precision | 0.8010 | 0.8155 |

## Duplicate sensitivity

8,542 of 82,332 test rows have an exact model-input duplicate in the training file;
524 of those disagree with the training label. Metrics excluding those rows:

| model | threshold | tp | fp | tn | fn | accuracy | precision | recall | f1 | fpr | average_precision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| majority_reference | 0.5000 | 38263 | 35527 | 0 | 0 | 0.5185 | 0.5185 | 1.0000 | 0.6829 | 1.0000 | n/a |
| rule_baseline | 0.5000 | 22762 | 5820 | 29707 | 15501 | 0.7111 | 0.7964 | 0.5949 | 0.6810 | 0.1638 | n/a |
| decision_tree | 0.4839 | 37072 | 10685 | 24842 | 1191 | 0.8391 | 0.7763 | 0.9689 | 0.8619 | 0.3008 | 0.9701 |
| isolation_forest | 0.7345 | 31387 | 12420 | 23107 | 6876 | 0.7385 | 0.7165 | 0.8203 | 0.7649 | 0.3496 | 0.7924 |
| mlp | 0.4874 | 37578 | 9658 | 25869 | 685 | 0.8598 | 0.7955 | 0.9821 | 0.8790 | 0.2718 | 0.9800 |
| hybrid_iso_rule | 0.7317 | 31490 | 12723 | 22804 | 6773 | 0.7358 | 0.7122 | 0.8230 | 0.7636 | 0.3581 | 0.8020 |

## Inference latency (wall clock, separate from simulated triage)

Hardware: Windows 11, Intel64 Family 6 Model 186 Stepping 2, GenuineIntel, 12 logical CPUs, Python 3.12.13. Batch 256 rows, 5 warm-up, 30 timed repetitions; milliseconds per batch.

| stage | p50 ms | p95 ms |
|---|---|---|
| preprocessing | 12.6210 | 21.2974 |
| majority_reference | 0.0052 | 0.0060 |
| rule_baseline | 2.0785 | 6.7068 |
| decision_tree | 0.5619 | 2.9714 |
| isolation_forest | 166.2867 | 284.1021 |
| mlp | 2.4106 | 6.2651 |
| hybrid_iso_rule | 167.8767 | 274.4732 |


## Triage and simulated response

Alerts from `hybrid_iso_rule`: 52,755 flagged, 5,000 written
(truncated: True). The analyst queue is a **simulation** driven by alert content alone (no labels) (policy: SIMULATED: escalate if a rule reason code is present, else dismiss; no labels used):
4,960 escalated, 40 dismissed, 0 still open. Simulated analyst delay
total 4,468,659 s is generated, not measured, and is not an incident response time.

## What this run does not establish

Public flow-record accuracy is not a national-security or operational-infrastructure outcome. No claim in the
source article about deployment, interviews or sector impact can be evaluated from this data.
