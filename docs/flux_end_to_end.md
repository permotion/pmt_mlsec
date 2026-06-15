# End-to-end flow — PMT MLSec

Complete flow from training trigger to production monitoring.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1 — MLOps: Trigger dag_model_a (Airflow UI)                            │
│                                                                              │
│   http://localhost:5080 → dag_model_a → Play                                 │
│                                                                              │
│   5 tasks:                                                                   │
│   verify_data → preprocess → train → register → evaluate                     │
│                                                                              │
│   Responsible: MLOps (trigger) | Automated: Airflow                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2 — Preprocess                                                          │
│                                                                              │
│   Script:      preprocess_csic_v4.py                                         │
│   Input:       data/raw/csic2010/csic_database.csv (61,065 rows)             │
│   Output:      data/processed/csic2010/features_v4.parquet (24 features)     │
│                                                                              │
│   Result:      ✅ SUCCESS — 61,065 rows processed                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3 — Train                                                               │
│                                                                              │
│   Script:      train_model_a_pipeline.py                                    │
│   Split:        70/15/15 (Train 42,745 / Val 9,160 / Test 9,160)            │
│   Model:        LightGBM with scale_pos_weight                               │
│   Threshold:    0.3002 (calibrated on val with min_recall=0.955)             │
│                                                                              │
│   Test metrics:                                                              │
│     ROC-AUC:   0.9661                                                        │
│     Recall:    0.9543 ✅ (≥ 0.95)                                            │
│     Precision: 0.7929 ✅ (≥ 0.75)                                             │
│     Gap:       0.0079 ✅ (≤ 0.05)                                             │
│                                                                              │
│   Result:      ✅ SUCCESS — Exit code 0                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4 — Register (automatic)                                                │
│                                                                              │
│   Script:      train_model_a_pipeline.py --register-only                     │
│                                                                              │
│   1. search_logged_models(source_run_id) → finds model_id                    │
│   2. mlflow.register_model(models:/<model_id>, EXPERIMENT)                  │
│   3. set_registered_model_alias(EXPERIMENT, "staging", version)            │
│   4. set_model_version_tag(EXPERIMENT, version, "deployment_stage",         │
│                              "candidate")                                    │
│                                                                              │
│   Result:      ✅ SUCCESS — New version with alias=staging, tag=candidate    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5 — MLflow Model Registry                                               │
│                                                                              │
│   Registered model:  mlsec-model-a                                           │
│                                                                              │
│   Current state (example with v4):                                          │
│     v4 — alias=staging, tag=candidate ← NEW CANDIDATE                        │
│     v3 — alias=archived                                                      │
│     v2 — alias=archived                                                      │
│     v1 — alias=archived                                                      │
│                                                                              │
│   Notification:  Blue Team alerted of new candidate in staging              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6 — Blue Team: Review and evaluation                                   │
│                                                                              │
│   Responsible: Blue Team                                                     │
│   Ref: [Blue Team Guide](blue_team/index.md)                                 │
│                                                                              │
│   Evaluation checklist:                                                      │
│                                                                              │
│   ☐ Training metrics:                                                       │
│       test_recall ≥ 0.95 ✅/❌                                               │
│       test_precision ≥ 0.75 ✅/❌                                             │
│       gap_recall ≤ 0.05 ✅/❌                                                 │
│                                                                              │
│   ☐ Production factors:                                                     │
│       Estimated FP rate (~17% with 0.3002 threshold) — acceptable?           │
│       Threshold trade-off: 0.3002 (high recall) vs 0.4723 (low FP)          │
│       Traffic volume and operational cost                                    │
│                                                                              │
│   ☐ Technical verification:                                                  │
│       GET /health → model_loaded=true                                        │
│       GET /features → correct threshold                                      │
│       Test with test request → coherent prediction                           │
│                                                                              │
│   Result:      ✅ APPROVED / ❌ REJECTED / ⚠️ APPROVED WITH ADJUSTMENTS       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌─────────────┴─────────────┐
                    │                           │
               ✅ APPROVED                    ❌ REJECTED
                    │                           │
                    ▼                           ▼
┌─────────────────────────────┐   ┌─────────────────────────────────────────┐
│ STEP 7a — Promote to Prod    │   │ STEP 7b — Keep current Prod             │
│                             │   │                                         │
│ Script:                     │   │   Document rejection reason             │
│ promote_model_to_production.py   │   │   Feedback to MLOps if necessary        │
│                             │   │   Request re-training if applicable     │
│ Actions:                    │   │                                         │
│ 1. set_alias(production)    │   │                                         │
│ 2. set_tag(deployment_stage,│   │                                         │
│    "production")             │   │                                         │
│ 3. Archive previous Prod     │   │                                         │
│                             │   │                                         │
│ Result: v4 → production      │   │                                         │
└─────────────────────────────┘   └─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 8 — API: FastAPI                                                        │
│                                                                              │
│   GET /health                                                                │
│     → {"status":"ok","model_loaded":true,"model_version":"v4-dag-..."}      │
│                                                                              │
│   POST /predict                                                              │
│     Normal request → probability: ~0.02 → prediction: 0                      │
│     Attack request → probability: ~0.9999 → prediction: 1                  │
│                                                                              │
│   Threshold in use: 0.3002                                                   │
│   Target latency: p95 < 500ms                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 9 — Production monitoring (continuous)                                 │
│                                                                              │
│   Responsible: Blue Team + AIOps                                             │
│                                                                              │
│   Metrics to watch:                                                          │
│     FP rate     < 20%    | Alert if > 20% for 3+ days                        │
│     Recall      ≥ 0.93   | Alert if < 0.93 for 3+ days                        │
│     Latency p95 < 500ms  | Alert if > 750ms for 1+ hour                      │
│     Availability > 99%   | Alert if < 98%                                    │
│                                                                              │
│   Actions by threshold:                                                      │
│     FP rate exceeded → Consider 0.4723 threshold or request re-training      │
│     Low recall       → Request re-training from MLOps                        │
│     High latency     → Investigate bottleneck or scale infrastructure        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 10 — Feedback loop                                                      │
│                                                                              │
│   Red Team Agent (every 6h):                                                 │
│    detect fresh payloads → report detection_rate_fresh                       │
│     If detection_rate_fresh < 85% → ALERT Blue Team                          │
│                                                                              │
│   AIOps (dag_batch_inference):                                              │
│     Analyzes logs → alert if attacks > 2 per batch                          │
│                                                                              │
│   Blue Team decides:                                                         │
│     detection_rate < 85% → Request re-training from MLOps                    │
│     Persistent high FP rate → Consider recalibrated threshold                │
│     New attack type → Document + request adjustment from MLOps               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Responsibility summary

| Step | Responsible | Automated |
|------|--------------|--------------|
| 1. Trigger | MLOps | Airflow |
| 2. Preprocess | — | ✅ |
| 3. Train | — | ✅ |
| 4. Register | — | ✅ |
| 5. Registry | — | — |
| 6. Evaluation | **Blue Team** | — |
| 7. Promotion | **Blue Team** | Script |
| 8. API | — | ✅ |
| 9. Monitoring | **Blue Team** + AIOps | Partial |
| 10. Feedback | Blue Team + Red Team | Partial |

---

## Current system version

| Component | Status | Detail |
|------------|---------|---------|
| dag_model_a | ✅ Active | Last run: v4 (a83d13be...) |
| MLflow Registry | ✅ v4 in production | alias=production, tag=production |
| API | ✅ Operational | http://localhost:5082 |
| Model version | v4-dag-2026-04-21 | threshold=0.3002 |