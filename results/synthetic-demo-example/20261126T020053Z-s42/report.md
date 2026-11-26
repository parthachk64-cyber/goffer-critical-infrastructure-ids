# Run report: 20261126T020053Z-s42

**Data label:** SYNTHETIC DEMONSTRATION (seeded generator; not real traffic)

Positive class: label == 1 (attack). Seed 42. Model version `infra-ids-0.1.0-seed42`,
source revision `57958ae63948d699ffb866174d47a6a951235085`. Every number below is regenerated from `predictions.csv` and
`manifest.json` in this directory by `python -m infra_ids report --run <dir>`.

## Inputs

| partition | file | SHA-256 | rows | label 0 | label 1 |
|---|---|---|---|---|---|
| train | synthetic_train.csv | `2bead8f1986240b4...` | 2,000 | 1,300 | 700 |
| test | synthetic_test.csv | `45904e60da9dd4b9...` | 1,000 | 650 | 350 |

Full hashes, ignored columns and the split are in `manifest.json`. Thresholds and preprocessing used the
fit/validation rows of the training file only (1,600 fit, 400 validation).

## Held-out results (all test rows, n=1,000, prevalence 0.3500)

| model | threshold | tp | fp | tn | fn | accuracy | precision | recall | f1 | fpr | average_precision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| majority_reference | 0.5000 | 0 | 0 | 650 | 350 | 0.6500 | n/a | 0.0000 | n/a | 0.0000 | n/a |
| rule_baseline | 0.5000 | 253 | 84 | 566 | 97 | 0.8190 | 0.7507 | 0.7229 | 0.7365 | 0.1292 | n/a |
| decision_tree | 0.5806 | 259 | 27 | 623 | 91 | 0.8820 | 0.9056 | 0.7400 | 0.8145 | 0.0415 | 0.9030 |
| isolation_forest | 0.9024 | 240 | 72 | 578 | 110 | 0.8180 | 0.7692 | 0.6857 | 0.7251 | 0.1108 | 0.8038 |
| mlp | 0.5331 | 241 | 10 | 640 | 109 | 0.8810 | 0.9602 | 0.6886 | 0.8020 | 0.0154 | 0.8835 |
| hybrid_iso_rule | 0.9406 | 245 | 70 | 580 | 105 | 0.8250 | 0.7778 | 0.7000 | 0.7368 | 0.1077 | 0.8089 |

Thresholds: maximise F1 on validation rows; ties to the higher threshold; reference models use 0.5 on a fixed score. `average_precision` is `n/a` for the majority and rule references
(constant or binary scores). Plots: `plots/confusion_matrices.png`, `plots/precision_recall.png`.

## Effect of adding the rule to the Isolation Forest (same records, same detector)

| | Isolation Forest | + rule (hybrid) |
|---|---|---|
| recall | 0.6857 | 0.7000 |
| precision | 0.7692 | 0.7778 |
| F1 | 0.7251 | 0.7368 |
| FPR | 0.1108 | 0.1077 |
| average precision | 0.8038 | 0.8089 |

## Duplicate sensitivity

0 of 1,000 test rows have an exact model-input duplicate in the training file;
0 of those disagree with the training label. Metrics excluding those rows:

| model | threshold | tp | fp | tn | fn | accuracy | precision | recall | f1 | fpr | average_precision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| majority_reference | 0.5000 | 0 | 0 | 650 | 350 | 0.6500 | n/a | 0.0000 | n/a | 0.0000 | n/a |
| rule_baseline | 0.5000 | 253 | 84 | 566 | 97 | 0.8190 | 0.7507 | 0.7229 | 0.7365 | 0.1292 | n/a |
| decision_tree | 0.5806 | 259 | 27 | 623 | 91 | 0.8820 | 0.9056 | 0.7400 | 0.8145 | 0.0415 | 0.9030 |
| isolation_forest | 0.9024 | 240 | 72 | 578 | 110 | 0.8180 | 0.7692 | 0.6857 | 0.7251 | 0.1108 | 0.8038 |
| mlp | 0.5331 | 241 | 10 | 640 | 109 | 0.8810 | 0.9602 | 0.6886 | 0.8020 | 0.0154 | 0.8835 |
| hybrid_iso_rule | 0.9406 | 245 | 70 | 580 | 105 | 0.8250 | 0.7778 | 0.7000 | 0.7368 | 0.1077 | 0.8089 |

## Inference latency (wall clock, separate from simulated triage)

Hardware: Windows 11, Intel64 Family 6 Model 186 Stepping 2, GenuineIntel, 12 logical CPUs, Python 3.12.13. Batch 256 rows, 5 warm-up, 30 timed repetitions; milliseconds per batch.

| stage | p50 ms | p95 ms |
|---|---|---|
| preprocessing | 14.1984 | 41.0799 |
| majority_reference | 0.0053 | 0.0057 |
| rule_baseline | 2.4270 | 6.1645 |
| decision_tree | 0.6319 | 4.6246 |
| isolation_forest | 193.1715 | 333.4413 |
| mlp | 1.1889 | 6.3756 |
| hybrid_iso_rule | 189.6277 | 418.9445 |


## Triage and simulated response

Alerts from `hybrid_iso_rule`: 315 flagged, 315 written
(truncated: False). The analyst queue is a **simulation** driven by alert content alone (no labels) (policy: SIMULATED: escalate if a rule reason code is present, else dismiss; no labels used):
298 escalated, 17 dismissed, 0 still open. Simulated analyst delay
total 285,539 s is generated, not measured, and is not an incident response time.

## What this run does not establish

Public flow-record accuracy is not a national-security or operational-infrastructure outcome. No claim in the
source article about deployment, interviews or sector impact can be evaluated from this data.
