# RACI Matrix — MLOps and Blue Team

## Roles and responsibilities

| Role | Main responsibility |
|---|---|
| **MLOps** | Training, candidate registration, pipeline maintenance |
| **Blue Team** | Validation, promotion to production, production monitoring |
| **Red Team** | Search for fresh payloads, adversarial testing, gap detection |
| **Airflow** | Training pipeline automation and Red Team Agent scheduling |

---

## Process: Detection Model Lifecycle

| Activity | MLOps | Blue Team | Airflow | Red Team |
|-----------|:-----:|:---------:|:-------:|:--------:|
| **1. Trigger training** | I | I | **R** | — |
| **2. Verify raw data** | I | — | **R** | — |
| **3. Preprocess features** | I | — | **R** | — |
| **4. Train model** | I | — | **R** | — |
| **5. Evaluate criteria** (recall≥0.95, precision≥0.75, gap≤0.05) | I | — | **R** | — |
| **6. Register in Staging** (if it passes criteria) | I | — | **R** | — |
| **7. Notify Blue Team** (new model in staging) | I | I | **R** | — |
| **8. Review model in Staging** (metrics, FP rate, threshold) | — | **R** | I | — |
| **9. Decide approval or rejection** | — | **A** | — | — |
| **10. Promote to Production** (if approved) | — | **R/A** | — | — |
| **11. Archive previous Production** | — | **R/A** | — | — |
| **12. API loads Production model** | — | — | **R** | — |
| **13. Monitor in production** (FP rate, latency) | I | **R** | I | — |
| **14. Search for fresh payloads** (Exploit-DB, CVE, etc.) | — | I | **R** | **R** |
| **15. Test payloads against API** | — | I | **R** | **R** |
| **16. Generate FN Report** | — | I | **R** | **R** |
| **17. Alert if detection_rate < 85% or FN ≥ 3** | — | **R** | — | **R** |
| **18. Evaluate Red Team gaps** | — | **R** | I | — |
| **19. Request re-training** (if gaps detected) | **R** | C | — | I |

---

### Code key

| Code | Meaning | Description |
|--------|-------------|-------------|
| **R** | Responsible | Executes the task directly |
| **A** | Accountable | Ultimately accountable, has authority to approve/reject |
| **C** | Consulted | Provides input before decisions — two-way communication |
| **I** | Informed | Notified of results — one-way communication |
| **—** | Not involved | Does not participate in this activity |

---

## Separation of responsibilities

### MLOps — What it can and cannot do

| Can | Cannot |
|-------|----------|
| Trigger training manually | Promote to Production |
| Modify training scripts | Modify threshold in production |
| Register models as `candidate` in Staging | Archive models |
| Receive feedback from Blue Team | Decide when a model goes to production |

### Blue Team — What it can and cannot do

| Can | Cannot |
|-------|----------|
| Review models in Staging | Modify training scripts |
| Approve or reject models | Modify the automated pipeline |
| Promote to Production | Delete MLflow runs |
| Archive previous Production | Re-train without MLOps |
| Recalibrate threshold in production | — |
| Request re-training from MLOps | — |

### Airflow — What it does automatically

| Automated | Detail |
|--------------|---------|
| `verify_data` | Verifies existence of the raw dataset |
| `preprocess` | Generates features_v4.parquet |
| `train` | Trains LightGBM, logs metrics |
| `register` | Registers in Staging if it passes criteria |
| `evaluate` | Verifies parquet integrity |

---

## Exception workflow

| Situation | Responsible | Required Action |
|-----------|--------------|------------------|
| Model does not pass criteria → not registered | Airflow (automatic) | MLOps notified via logs |
| Blue Team rejects model in Staging | Blue Team | Documented feedback for MLOps |
| FP rate exceeds 20% in production | Blue Team | Recalibrate threshold or request re-training |
| Red Team detects detection rate < 85% | Blue Team + Red Team | Request re-training from MLOps |
| API does not respond (503) | Blue Team + AIOps | Verify that Production model exists |

---

## Approval workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                     BLUE TEAM APPROVAL                          │
│                                                                 │
│  1. Review v4 in Staging → metrics + FP rate                    │
│                                                                 │
│  2. Approves?                                                  │
│         │                                                        │
│    ┌────┴────┐                                                  │
│    │Yes      │No                                                 │
│    ▼         ▼                                                  │
│  Promote   Keep current                                         │
│  to Prod   Production                                           │
│    │         │                                                  │
│    ▼         ▼                                                  │
│  v4 → prod  Archive decision                                    │
│  v3 → arch  in logs                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Production monitoring metrics

| Metric | Target | Responsible | Action if exceeded |
|---------|--------|-------------|-----------------|
| FP rate | < 20% | Blue Team | Recalibrate threshold (0.4723) |
| Recall | ≥ 0.95 | Blue Team | Request re-training from MLOps |
| API Latency | < 500ms p95 | AIOps | Scale infrastructure |
| Availability | > 99% | AIOps | Alert Blue Team |
| Detection rate (Red Team) | ≥ 85% | Red Team | Alert Blue Team + request re-training |

---

## References

- [Complete MLOps + AIOps + Blue Team workflow](mlops_aiops_blue_team.md)
- [Red Team — Practical Guide](red_team/index.md)
- [Red Team Agent — Technical Documentation](red_team_agent.md)
- [Model Registry](model_registry.md)
- [Inference API](api.md)
