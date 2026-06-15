# Red Team — Practical Guide

Section for the Red Team. Here you will find the activities, hands-on tests, and metrics that define the Red Team role in the PMT MLSec system.

---

## What is the Red Team in this context

The Red Team is not a real penetration testing team. It is an **automated adversarial testing agent** that:

1. **Searches for fresh payloads** in public sources (Exploit-DB, CVE feeds, PayloadAllTheThings)
2. **Tests them against the API** (`POST /predict`) to detect false negatives
3. **Reports gaps** to the Blue Team so they can request re-training from MLOps

The goal is to close the gap between the training dataset (CSIC 2010, 2010) and current real attacks.

---

## Red Team Activities

| # | Activity | Periodicity | Automated |
|---|-----------|-------------|--------------|
| 1 | [Search for fresh payloads](#1-search-for-fresh-payloads) | Every 6h (via DAG) | Partial |
| 2 | [Test payloads against the API](#2-test-payloads-against-the-api) | Every cycle | Partial |
| 3 | [Generate FN Report](#3-generate-fn-report) | Every cycle | Yes |
| 4 | [Evaluate detection rate](#4-evaluate-detection-rate) | Every cycle | Yes |
| 5 | [Alert if threshold exceeded](#5-alert-if-threshold-exceeded) | When FN > 3 | Yes |
| 6 | [Manual gap analysis](#6-manual-gap-analysis) | On demand | No |

---

## 1. Search for fresh payloads

### Monitored sources

| Source | Type | Categories | Scheduling |
|--------|------|-----------|------------|
| Exploit-DB | Web (HTTP/SQLi/XSS/RCE) | SQL injection, XSS, LFI, RCE | Every 6h |
| PayloadAllTheThings (GitHub) | Web attacks | Polyglots, bypass techniques | Daily |
| NVD CVE Feed | Web CVEs last 90 days | Recent vulnerabilities | Every 12h |
| OWASP Cheat Sheets | Attack patterns | Reference baseline | Weekly |

### Inclusion criteria

A payload is processed if:
- **It is HTTP-based** —SQLi, XSS, path traversal, command injection, etc.
- **It is relevant to Model A** — web attacks matching CSIC scope
- **It is fresh** — does not exist in training dataset (hash comparison)
- **It is reproducible** — has enough context to build the HTTP request

### Exclusion criteria

- Buffer overflow, kernel exploits, binary exploits
- Non-HTTP protocols (SMTP, FTP, SSH)
- Payloads without enough documentation

### Hands-on: Verify sources

```bash
# Verify Exploit-DB is accessible
curl -s "https://www.exploit-db.com" | grep -o "exploits" | head -1

# Verify PayloadAllTheThings access (GitHub raw content)
curl -s "https://raw.githubusercontent.com/swisskyrepo/PayloadsAllTheThings/master/README.md" | head -50

# Verify NVD API
curl -s "https://services.nvd.nist.gov/rest/json/cves/2.0?pubStartDate=$(date -v-90d +%Y-%m-%d)T00:00:00.000&keywords=web" | python3 -c "import sys,json; c=json.load(sys.stdin); print(f'CVE count: {len(c.get(\"vulnerabilities\",[]))}')"
```

---

## 2. Test payloads against the API

### Used endpoint

```
POST http://localhost:5082/predict
Content-Type: application/json

{
  "request": "<HTTP request string>",
  "method": "GET|POST",
  "url": "/endpoint",
  "headers": {...},
  "body": "..."
}
```

### How testing works

1. Raw payload is converted to valid HTTP request
2. URL encoding is applied if necessary
3. Sent to `/predict`
4. Logged: `{prediction, probability, detected}`

**Detected** = `prediction == 1` (attack)

**Not detected (FN)** = `prediction == 0` + is actually an attack

### Hands-on: Manual test

```bash
# Test 1: Basic SQL Injection
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{"request": "GET /search?id=1%27+OR+%271%27%3D%271 HTTP/1.1\\r\\nHost: target.com"}'

# Test 2: Basic XSS
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{"request": "GET /comment?text=<script>alert(1)</script> HTTP/1.1\\r\\nHost: target.com"}'

# Test 3: Path traversal
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{"request": "GET /download?file=../../etc/passwd HTTP/1.1\\r\\nHost: target.com"}'
```

### Interpret results

| Result | `prediction` | `probability` | Meaning |
|-----------|-------------|---------------|-------------|
| Attack detected | `1` | ~0.99 | ✅ Model working correctly |
| Attack FN | `0` | ~0.05 | ❌ Model missed it — gap |
| Normal request | `0` | ~0.02 | ✅ Model working correctly |
| Normal FP | `1` | ~0.95 | ❌ FP — Blue Team should investigate |

---

## 3. Generate FN Report

### FN Report Structure

```markdown
# Red Team FN Report
Generated: 2026-04-21T14:30:00Z
API: http://localhost:5082
Model: v4-dag-2026-04-21
Threshold: 0.3002

## Summary
| Metric | Value |
|---------|-------|
| Total tested payloads | 47 |
| Detected | 44 |
| Not detected (FN) | 3 |
| Detection rate | 93.6% |

## False Negatives

### 1. SQL Injection — boolean-based blind
- **Payload:** ' OR (SELECT 1 FROM users WHERE id=1)=1 --
- **Source:** https://www.exploit-db.com/exploits/51234
- **Category:** SQLi
- **HTTP Request:** GET /login?id=' OR (SELECT 1...
- **Probability:** 0.12
- **Prediction:** 0 ❌

### 2. XSS — polyglot
...

## Recommendations
- Detection rate (93.6%) is above the threshold (85%) — OK
- FN found: SQLi bypass, XSS polyglot — review with MLOps
```

### Hands-on: Generate report manually

```bash
# Go to reports directory
cd /Users/permotion/Desktop/repositories/PERMOTION/PMT\ MLSec/data/reports/red_team

# Create report with timestamp
REPORT_DATE=$(date +"%Y-%m-%dT%H:%M:%SZ")
cat > fn_report_$REPORT_DATE.md << 'EOF'
# Red Team FN Report
Generated: TIMESTAMP

## Summary
| Metric | Value |
|---------|-------|
| Total tested payloads | N |
| Detected | N |
| Not detected (FN) | N |
| Detection rate | X% |

## False Negatives
(detail each FN)
EOF
```

### Reports location

```
data/reports/red_team/
├── fn_report_2026-04-21T14:30:00Z.md
├── fn_report_2026-04-21T20:30:00Z.md
└── fn_report_2026-04-22T02:30:00Z.md
```

---

## 4. Evaluate detection rate

### Alert threshold

| Metric | Threshold | Action if unmet |
|---------|-----------|---------------------|
| `detection_rate_fresh` | ≥ 85% | Alert to Blue Team |
| `fn_count` | < 3 per cycle | No alert |
| `fn_count` | ≥ 3 per cycle | Alert to Blue Team |

### How it is calculated

```
detection_rate = (detected_payloads / total_payloads) × 100
```

### Interpretation

| Detection rate | Meaning | Action |
|----------------|-------------|--------|
| ≥ 95% | Excellent — very effective model | Continue monitoring |
| 85% - 94% | Acceptable — some gaps | Review FN reports |
| 70% - 84% | Low — significant gaps | Alert + request re-training |
| < 70% | Critical — outdated model | Urgent alert + immediate re-training |

### Hands-on: Calculate detection rate

```python
# Calculation example
total_payloads = 50
detected = 44
fn_count = 6

detection_rate = (detected / total_payloads) * 100
print(f"Detection rate: {detection_rate:.1f}%")  # 88.0%

# Verify if exceeds threshold
RT_DETECTION_THRESHOLD = 85
if detection_rate < RT_DETECTION_THRESHOLD:
    print("⚠️ ALERT: Detection rate below threshold!")
```

---

## 5. Alert if threshold exceeded

### Alert conditions

An alert is sent when:
- `detection_rate < 85%` (any amount of FN)
- `fn_count ≥ 3` (even if detection rate is OK)

### Alert destinations

| Destination | Trigger | Format |
|---------|---------|---------|
| Local file | Always | `reports/red_team/fn_report_{timestamp}.md` |
| Blue Team (Slack) | `alert_triggered=True` | Block kit message |
| Airflow DAG | `alert_triggered=True` | Trigger `dag_red_team_alert` |

### Alert structure (Slack)

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {"type": "plain_text", "text": "🚨 Red Team Alert — Low Detection Rate"}
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Detection Rate:* 78.5%"},
        {"type": "mrkdwn", "text": "*FN Count:* 5"},
        {"type": "mrkdwn", "text": "*Threshold:* 85%"},
        {"type": "mrkdwn", "text": "*Model:* v4-dag-2026-04-21"}
      ]
    },
    {
      "type": "section",
      "text": {"type": "mrkdwn", "text": "*Undetected payloads:*\n• SQLi boolean-based blind\n• XSS polyglot\n• ... (list)"}
    },
    {
      "type": "actions",
      "elements": [
        {"type": "button", "text": {"type": "plain_text"}, "action_id": "view_report"}
      ]
    }
  ]
}
```

### Hands-on: Send manual alert

```bash
# Basic curl alert (Slack webhook)
WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

curl -X POST $WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{
    "text": "🚨 Red Team Alert: Detection rate 78.5% < 85% threshold. 5 FNs detected.",
    "blocks": [
      {"type": "section", "text": {"type": "mrkdwn", "text": "*Detection Rate:* 78.5% (threshold: 85%)\n*FN Count:* 5\n*Undetected payloads:* SQLi bypass, XSS polyglot"}}
    ]
  }'
```

---

## 6. Manual gap analysis

### Post-FN Report Analysis

When a FN Report arrives, Red Team should:

1. **Categorize FNs** — what type of attacks are not detected
2. **Identify patterns** — are they all SQLi? XSS? specific type?
3. **Evaluate severity** — a SQLi FN is more critical than a stored XSS
4. **Propose action** — re-training, threshold adjustment, or ignore

### Attack categories to evaluate

| Category | Examples | Severity |
|-----------|----------|-----------|
| SQL Injection | boolean-based, union-based, time-based blind | 🔴 High |
| XSS | Reflected, Stored, DOM-based, polyglots | 🔴 High |
| Path Traversal | ../../etc/passwd, null byte injection | 🟡 Medium |
| Command Injection | ; ls, |, $() | 🔴 High |
| LDAP Injection | *)(uid=*)|cn=admin | 🟡 Medium |
| XML Injection | XXE, XPath injection | 🟡 Medium |
| Webshell | <?php system($_GET['cmd']) ?> | 🔴 High |

### Hands-on: Manual gap analysis

```bash
# 1. List recent FN reports
ls -la data/reports/red_team/ | tail -5

# 2. View FNs from last report
cat data/reports/red_team/fn_report_2026-04-22T02:30:00Z.md

# 3. Count FNs by category
grep -h "Category:" data/reports/red_team/*.md | sort | uniq -c | sort -rn

# 4. Verify if there are new patterns
grep -h "Payload:" data/reports/red_team/*.md | sort | uniq -c | sort -rn | head -10
```

### Gap severity matrix

| Gap | Category | FN count (last month) | Severity | Action |
|-----|-----------|----------------------|-----------|--------|
| SQLi bypass techniques | SQL Injection | 12 | 🔴 High | Request re-training |
| XSS polyglots | XSS | 8 | 🔴 High | Request re-training |
| Path traversal simple | Path Traversal | 3 | 🟡 Medium | Monitoring |
| Command injection | Command Injection | 7 | 🔴 High | Request re-training |

---

## 7. Periodic hands-on tests

### Test 1: Verify API is responding

```bash
# Health check
curl http://localhost:5082/health

# Expected: {"status":"ok","model_loaded":true,"model_version":"v4-dag-..."}
```

### Test 2: Test known attack (should be detected)

```bash
# SQL Injection — must be detected (prediction=1)
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{"request": "GET /search?id=1%27+UNION+SELECT+NULL-- HTTP/1.1\\r\\nHost: target.com"}'

# Expected: {"prediction":1,"probability":0.99...}
```

### Test 3: Test normal request (should NOT be detected)

```bash
# Normal request — must pass as normal (prediction=0)
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{"request": "GET /products?category=electronics HTTP/1.1\\r\\nHost: target.com"}'

# Expected: {"prediction":0,"probability":0.02...}
```

### Test 4: Verify threshold and probabilities

```bash
# With threshold 0.3002:
# - probability < 0.3002 → prediction 0 (normal)
# - probability >= 0.3002 → prediction 1 (attack)

# Borderline test: probability near threshold
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d '{"request": "GET /search?q=test HTTP/1.1\\r\\nHost: target.com"}'

# Review the "probability" field in the response
```

### Test 5: Report FN manually

```bash
# If you detect an FN (attack not detected):
# 1. Document in FN report
# 2. Send alert if exceeds threshold

# Example: SQLi bypass not detected
PAYLOAD="' OR (SELECT 1 FROM users)=1--"
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d "{\"request\": \"GET /login?user=admin&pass=$PAYLOAD HTTP/1.1\\r\\nHost: target.com\"}"

# If prediction=0 → Confirmed FN
```

---

## 8. Integration with Blue Team and MLOps

### Communication flow

```
Red Team Agent                    Blue Team                    MLOps
      │                             │                           │
      │─ FN Report ────────────────▶│                           │
      │─ Alert if threshold ───────▶│                           │
      │                             │─ Evaluate gaps ──────────▶│
      │                             │─ Request re-training ────▶│
      │                             │                           │
      ◀─── Gap feedback ◀───────────│                           │
      │                             │◀─── New model in staging ◀│
      │─ Test new model ───────────▶│                           │
```

### What Red Team reports to Blue Team

| Report | Content | Timing |
|---------|-----------|--------|
| FN Report | List of undetected payloads + detection rate | Every cycle (6h) |
| Alert | detection_rate < 85% or fn_count ≥ 3 | Immediate |
| Gap Analysis | FN patterns by category + severity | Weekly |

### What Red Team receives from Blue Team

| Input | Description |
|-------|-------------|
| Gap feedback | Is the FN valid or was it a misclassified FP? |
| Re-training decision | Was re-training requested from MLOps? |
| New model in staging | To compare detection rate between versions |

### Hands-on: Communication check

```bash
# Verify Red Team → Blue Team channel is active
# 1. Check that reports directory exists
ls -la data/reports/red_team/

# 2. View latest FN reports
tail -20 data/reports/red_team/*.md | head -50

# 3. Verify Airflow DAG exists and is active
docker compose -f docker/docker-compose.yml exec airflow-webserver airflow dags list | grep red_team
```

---

## 9. Red Team Metrics

### Cycle metrics

| Metric | Description | Target |
|---------|-------------|--------|
| `detection_rate_fresh` | % fresh payloads detected | ≥ 85% |
| `fn_count` | Amount of FNs in cycle | < 3 |
| `payloads_tested` | Total payloads processed | > 0 |
| `sources_queried` | Sources queried in cycle | 3+ |
| `execution_time_s` | Total cycle time | < 10 min |
| `false_positive_rate` | Red Team FP (invented attacks detected) | < 5% |

### Trend metrics (historical)

| Metric | Description | Target |
|---------|-------------|--------|
| `avg_detection_rate` | detection_rate mean last 7 days | ≥ 85% |
| `worst_detection_rate` | Worst detection_rate in 7 days | ≥ 80% |
| `fn_trend` | FN count trend (up/down) | Decreasing |
| `new_attack_categories` | Unseen FN categories | 0 (ideal) |

### Metrics dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ RED TEAM METRICS — Last cycle                               │
│                                                             │
│ Detection Rate: 93.6% ✅ (target: 85%)                     │
│ FN Count: 3 ⚠️ (threshold: 3, at limit)                    │
│ Payloads Tested: 47                                         │
│ Sources Queried: 5                                          │
│ Execution Time: 8m 23s ✅                                  │
│                                                             │
│ FN by category:                                            │
│   SQL Injection: 2                                          │
│   XSS: 1                                                    │
│   Path Traversal: 0                                        │
│                                                             │
│ Trend (7 days):                                            │
│   Detection Rate: 92.3% → 93.6% ↑ (+1.3%)                 │
│   FN Count: 5 → 3 ↓ (-40%)                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. Red Team Activity Checklist

### Before each cycle

```
☐ Verify API is operational (GET /health)
☐ Verify latest FN report exists
☐ Confirm payload sources accessible
```

### After each cycle

```
☐ FN Report generated and saved in data/reports/red_team/
☐ Detection rate calculated
☐ Alert sent if threshold exceeded
☐ Metrics logged (if MLflow integration active)
```

### Weekly review

```
☐ Analyze detection rate trends
☐ Identify new FN patterns
☐ Propose actions to Blue Team (re-training, threshold)
☐ Verify dag_red_team_agent DAG is active
☐ Review Red Team false positives (if any)
```

---

## Test Scenarios

### Scenario 1: FN in SQL Injection

**Context:** Red Team detects a SQL injection bypass is not detected.

```bash
# Payload
PAYLOAD="' OR (SELECT 1 FROM users WHERE id=1)=1 --"

# Send to API
curl -X POST http://localhost:5082/predict \
  -H "Content-Type: application/json" \
  -d "{\"request\": \"GET /login?user=admin&pass=$PAYLOAD HTTP/1.1\\r\\nHost: target.com\"}"

# Expected result (bad): prediction=0, probability=0.12 → FN
# Correct result: prediction=1, probability=0.98
```

**Action:** Document in FN Report, alert if new pattern.

---

### Scenario 2: Low detection rate

**Context:** Last cycle detection rate was 78% (below 85% threshold).

```bash
# Verify
echo "Detection rate: 78% (threshold: 85%)"
echo "FN count: 6"

# Alert
# → Slack: "🚨 Red Team Alert: Detection rate 78% < 85%"
# → Include FN list
# → Request Blue Team review
```

**Action:** Alert immediately, document in FN Report, request re-training.

---

### Scenario 3: New attack type

**Context:** Red Team finds a recent CVE not matching existing categories.

```bash
# CVE-2024-1234: HTTP Request Smuggling
# Payload is not SQLi, not XSS, not path traversal
# It is a new vector: HTTP desync/request smuggling

# Test
PAYLOAD="GET / HTTP/1.1\r\nHost: target.com\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nGET /admin HTTP/1.1\r\nHost: target.com"
```

**Action:** Document as new category "HTTP Desync", severity 🔴 High, request re-training with new data.

---

## References

- [Red Team Agent — Technical Documentation](red_team_agent.md)
- [Blue Team Guide](blue_team/index.md)
- [End-to-end Flow](flux_end_to_end.md)
- [RACI — Responsibility Matrix](raci_model_lifecycle.md)
- [Inference API](api.md)