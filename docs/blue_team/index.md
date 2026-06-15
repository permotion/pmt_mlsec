# Blue Team — Guide

Section for the Blue Team. Here you will find all tasks, decision factors and metrics for managing the model lifecycle in production.

---

## Blue Team Tasks

| # | Task | Periodicity | Automated |
|---|-------|-------------|--------------|
| 1 | [Review models in Staging](#1-review-models-in-staging) | When new candidate appears | No |
| 2 | [Evaluate decision factors](#2-evaluate-decision-factors) | During staging review | No |
| 3 | [Approve or reject model](#3-approve-or-reject-model) | After evaluation | No |
| 4 | [Promote to Production](#4-promote-to-production) | If approved | Yes (script) |
| 5 | [Monitor in production](#5-monitor-in-production) | Continuous | Partial |
| 6 | [Investigate false positives](#6-investigate-false-positives) | When alerts are detected | No |
| 7 | [Evaluate Red Team gaps](#7-evaluate-red-team-gaps) | Each red team report | No |
| 8 | [Request MLOps re-training](#8-request-mlops-re-training) | If gaps are detected | No |

---

## 1. Review models in Staging

### How to do it

1. Open MLflow UI: http://localhost:5081
2. Go to **Models** → select `mlsec-model-a`
3. Filter by **Stage: Staging**
4. Click on the version to view details

### What to review

| Field | Description |
|-------|-------------|
| **Version** | Version number (e.g. v4) |
| **Run ID** | MLflow run identifier |
| **Training metrics** | test_recall, test_precision, test_roc_auc, gap_recall |
| **Calibrated threshold** | Value used in training (0.3002) |
| **Training date** | trained_at tag |
| **deployment_stage** | Must be `candidate` |

### Decision factors

- Do training metrics meet minimum criteria?
- How long ago was it trained? (if weeks have passed, consider re-training with fresher data)

---

## 2. Evaluate decision factors

Before approving or rejecting, the Blue Team must evaluate these factors:

### 2.1 Training metrics (minimum criteria)

| Metric | Criterion | Target |check |
|---------|----------|--------|------|
| `test_recall` | ≥ 0.95 | Detect 95% of attacks | ✅/❌ |
| `test_precision` | ≥ 0.75 | Less than 25% false alarms | ✅/❌ |
| `gap_recall` | ≤ 0.05 | Low overfitting risk | ✅/❌ |
| `test_roc_auc` | ≥ 0.95 | Excellent discriminative capacity | ✅/❌ |

### 2.2 FP rate in production (estimated)

The training threshold (0.3002) is calibrated for a dataset with **41% attacks**. In production, typical traffic has ~**1% attacks**.

| Threshold | Recall (99:1 traffic) | FP rate | Precision |
|-----------|----------------------|---------|-----------|
| 0.3002 (training) | ~100% | ~17.4% | ~5.5% |
| 0.4723 (recalibrated) | ~96.3% | ~12.7% | ~7.5% |

**Key question:** Is a ~17% FP rate tolerable given our traffic volume?

### 2.3 Traffic volume and operational cost

| Factor | How to estimate it |
|--------|----------------|
| Daily requests | API logs or system capacity |
| Expected FPs per day | `daily_requests × 0.17` |
| Investigation time per FP | ~15-30 min per investigation |
| Monthly operational cost | `monthly_FP × time_per_fp × hourly_cost` |

**Example:** If there are 10,000 requests/day with 17% FP:
- ~1,700 FPs per day
- ~510 FPs per month (if only business days are added)
- With 20 min per investigation: ~170 hours/month just on FPs

### 2.4 Recall vs Precision trade-off in production

| Scenario | If you prioritize Recall | If you prioritize Precision |
|-----------|---------------------|------------------------|
| FP rate | High (~17%) | Low (~12%) |
| Detected attacks | ~100% | ~96% |
| Operational load | High | Medium |
| Recommended when | Attacks are critical | Limited resources |

### 2.5 API Latency

Verify that the API has acceptable latency:

| Metric | Target |check |
|---------|--------|------|
| p50 latency | < 100ms | ✅/❌ |
| p95 latency | < 500ms | ✅/❌ |
| p99 latency | < 1000ms | ✅/❌ |

### 2.6 Availability

| Metric | Target |check |
|---------|--------|------|
| Uptime | > 99% | ✅/❌ |
| Incidents per month | < 2 | ✅/❌ |

---

## 3. Approve or reject model

### Decision checklist

```
Does it meet training criteria?
  ☐ test_recall ≥ 0.95
  ☐ test_precision ≥ 0.75
  ☐ gap_recall ≤ 0.05

Is FP rate acceptable for our context?
  ☐ We understand the estimated FP rate (~17% with 0.3002 threshold)
  ☐ We have capacity to investigate the generated FPs

Is the threshold adequate for production?
  ☐ Use training threshold (0.3002) — higher recall, more FPs
  ☐ Use recalibrated threshold (0.4723) — lower recall, fewer FPs

Is API latency acceptable?
  ☐ p95 < 500ms

Are there active alerts from AIOps or Red Team?
  ☐ No pending FP excess alerts
  ☐ No gaps detected by Red Team
```

### Possible decisions

| Decision | Action | Result |
|-----------|------|-----------|
| **Approve** | Promote to Production | Use `promote_model_to_production.py` script |
| **Reject** | Stick with current Production | Document reason in logs |
| **Approve with adjustments** | Request re-training with different threshold | Create ticket for MLOps |

---

## 4. Promote to Production

### Script (automatic)

```bash
cd /Users/permotion/Desktop/repositories/PERMOTION/PMT MLSec
MLFLOW_TRACKING_URI=http://mlflow:5000 python scripts/promote_model_to_production.py
```

### What the script does

1. Finds the model with `staging` alias
2. Displays candidate model metrics
3. Archives previous Production (if exists) → `archived` alias
4. Sets `production` alias on the new model
5. Sets `deployment_stage=production` and `promoted_at` tags

### Post-promotion verification

| Step | Verification | Expected |
|------|--------------|----------|
| 1 | `GET /health` | `{"status":"ok","model_loaded":true}` |
| 2 | `GET /features` | correct `threshold` |
| 3 | Test with known request | coherent `prediction` |

---

## 5. Monitor in production

### Metrics to watch

| Metric | Target | Alert if |
|---------|--------|-----------|
| **FP rate** | < 20% | > 20% for 3 consecutive days |
| **Recall** | ≥ 0.95 | < 0.93 for 3 consecutive days |
| **Latencia p95** | < 500ms | > 750ms for 1 hour |
| **Disponibilidad** | > 99% | < 98% |

### How to get metrics

```bash
# View API logs
docker compose -f docker/docker-compose.yml logs api --tail=100

# View health status
curl http://localhost:5082/health

# View model metrics
curl http://localhost:5082/features
```

### Actions based on exceeded thresholds

| Metric | Exceeded | Action |
|---------|----------|--------|
| FP rate > 20% | For 3+ days | Consider recalibrated threshold (0.4723) or request re-training |
| Recall < 93% | For 3+ days | Request MLOps re-training |
| p95 latency > 750ms | For 1+ hour | Scale infrastructure or investigate bottleneck |
| Availability < 98% | Any | Investigate root cause immediately |

---

## 6. Investigate false positives

### What is a false positive

A normal request classified as an attack (`prediction=1`).

### How to investigate

1. **Identify the request** — review API logs with timestamp
2. **Classify the request**:
   - Was it really normal? → Confirmed FP
   - Was it an undetected attack before? → Model review needed
3. **Document** — save in log if there is a new attack pattern

### Alert threshold

The `dag_batch_inference` DAG alerts when `detected_attacks > 2` per batch.

---

## 7. Evaluate Red Team gaps

The Red Team Agent generates reports with:

| Metric | Description |
|---------|-------------|
| `detection_rate_fresh` | % of fresh payloads detected |
| `false_negatives` | Undetected attacks |
| `FN_rate` | `false_negatives / total_payloads` |

### Thresholds

| Metric | Threshold | Action if unmet |
|---------|-----------|---------------------|
| `detection_rate_fresh` | ≥ 85% | Request re-training |
| `FN_rate` | < 15% | Request re-training |

### Evaluation process

1. Receive Red Team report (`reports/red_team/`)
2. Verify `detection_rate_fresh` ≥ 85%
3. If unmet: analyze what type of payloads are not detected
4. Document found gap
5. Create re-training request for MLOps

---

## 8. Request MLOps re-training

### When to request

| Condition | Priority | Detail |
|-----------|-----------|---------|
| FP rate > 20% for 3+ days | High | Attach log data |
| Recall < 93% for 3+ days | High | Attach production metrics |
| Detection rate fresh < 85% | High | Attach Red Team report |
| New attack type detected | Medium | Document attack pattern |

### How to make the request

1. Document:
   - Which metric failed
   - When the problem started
   - Supporting data (logs, captures, reports)
2. Send to MLOps team
3. MLOps evaluates and decides whether to trigger re-training

---

## Metrics summary

| Metric | Training | Production | Alert |
|---------|----------|------------|--------|
| Recall | ≥ 0.95 | ≥ 0.93 | < 0.93 |
| Precision | ≥ 0.75 | — | — |
| Gap recall | ≤ 0.05 | — | — |
| ROC-AUC | ≥ 0.95 | — | — |
| FP rate | — | < 20% | > 20% |
| p95 latency | — | < 500ms | > 750ms |
| Availability | — | > 99% | < 98% |
| Detection rate (Red Team) | — | ≥ 85% | < 85% |

---

## References

- [RACI — Responsibility Matrix](raci_model_lifecycle.md)
- [MLflow Model Registry](model_registry.md)
- [Full workflow](mlops_aiops_blue_team.md)
- [Inference API](api.md)
- [Red Team — Practical Guide](../red_team/index.md)