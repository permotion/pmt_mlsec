# Red Team Agent — Continuous Adversarial Testing

## Overview

### What it is

An automated system based on CrewAI that monitors public payload sources, executes them against Model A's inference API, and reports which attacks were not detected (false negatives).

**Goal:** close the gap between the training dataset (CSIC 2010) and real attacks that appear after deployment. The Red Team generates fresh inputs that feed the Blue Team and MLOps feedback loop.

### Why

The CSIC 2010 dataset is from 2010. Web attacks evolve constantly:
- New SQL injection bypass techniques
- Fresh XSS polyglots
- Novel encoder combinations
- Emerging API-specific attack patterns

The model might have good test set metrics but low coverage against new techniques. This agent acts as a **canary** that detects regressions before they impact production.

### How it integrates into existing workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                      FULL WORKFLOW                              │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ MLOps    │───▶│  Staging │───▶│ Red Team  │───▶│ Blue Team│  │
│  │ (train)  │    │ (MLflow) │    │ (Agent)   │    │(validate)│  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                            │            │        │
│                                            ▼            ▼        │
│                                    ┌──────────────┐  ┌────────┐  │
│                                    │  FN Report   │  │Production│  │
│                                    │  (gaps)      │  │(API)   │  │
│                                    └──────────────┘  └────────┘  │
│                                            │                      │
│                                            ▼                      │
│                                    ┌──────────────┐               │
│                                    │ MLOps (re-   │               │
│                                    │ training)    │               │
│                                    └──────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

**Role of each team:**

| Team | Role in this workflow |
|---|---|
| **MLOps** | Receives FN reports → incorporates payloads into dataset → re-trains |
| **Red Team Agent** | Autonomously searches for fresh payloads → tests them against API → reports FN |
| **Blue Team** | Consumes FN reports → decides which gaps to prioritize → approves/rejects models |

---

## Architecture

### Crew: `red_team_crew`

```
PayloadHunterAgent (researcher)
        │
        ▼ searches for fresh payloads
AttackSimulatorAgent (attacker)
        │
        ▼ formats + sends to /predict
        │
        ▼
ReporterAgent (analyst)
        │
        ├── FN > threshold → ALERT → Blue Team + MLOps
        └── Logging for detection_rate trend
```

### Data flow diagram

```
1. PayloadHunterAgent
   Input:  Configured sources (see Data Sources section)
   Output: List of raw payloads (strings)

2. AttackSimulatorAgent
   Input:  Raw payload
   Output: Formatted HTTP request → POST /predict
           → {prediction: 0|1, probability: float}

3. ReporterAgent
   Input:  Results of multiple payloads
   Output: FN Report (markdown)
           + Metrics to logging (detection_rate, fn_count)
           + Alert if threshold exceeded
```

---

## Data Sources

### Monitored sources

| Source | URL / Type | Category of interest | Frequency |
|---|---|---|---|
| Exploit-DB | https://www.exploit-db.com | HTTP, SQLi, XSS, RCE | Every 6h |
| PayloadAllTheThings | GitHub (swisskyrepo/PayloadsAllTheThings) | Web Attacks | Daily |
| BugBounty Programs | HackerOne, BugCrowd | Real-world payloads | Daily |
| CVE Feeds | NVD (nvd.nist.gov) | Recent web CVEs | Every 12h |
| OWASP Cheat Sheets | OWASP | Attack patterns | Weekly |

### Filtering criteria

A payload is processed if it meets **all** these conditions:

1. **It is HTTP-based** — has an HTTP request (no binary exploits, no local priv escalation)
2. **It is reachable by Model A** — is SQLi, XSS, path traversal, or similar to CSIC scope
3. **It is fresh** — does not exist in CSIC 2010 dataset (hash comparison)
4. **It is not duplicate** — payload hash did not appear in last 24h

### Discard criteria

- **Buffer overflow**, **kernel exploits**, **physical attacks** payloads
- **External API** payloads that are not HTTP (SMTP, FTP, etc.)
- Payloads without enough documentation to reproduce the request

---

## Agent Definitions

### PayloadHunterAgent

**Role:** `Threat Intelligence Researcher`
**Goal:** Find fresh, relevant attack payloads from public sources that could evade the current detection model
**Backstory:** You are a senior red team operator who monitors multiple threat intelligence feeds daily. You know which sources are reliable and how to extract actionable payloads from unstructured data.

**Available tools:**
- `WebSearch` — search exploit-db, github
- `WebFetch` — extract details of a specific exploit
- `GitHub` — monitor payload repositories

**Output:** List of `Payload(source, url, description, category, raw_payload, date_found)` objects

---

### AttackSimulatorAgent

**Role:** `Web Attack Simulator`
**Goal:** Transform a raw payload into a valid HTTP request and test it against the MLSec API
**Backstory:** You are an expert penetration tester who can take any attack payload and craft a syntactically correct HTTP request. You understand URL encoding, HTTP headers, and how to structure requests that match what the model expects.

**Available tools:**
- `HttpRequest` — send formatted request to API
- `URLEncoder` — encoding utilities

**Input:** `Payload` object
**Process:**
1. Parse raw payload
2. Determine HTTP method (GET/POST according to payload)
3. Apply URL encoding if necessary
4. Build full HTTP request (method, url, headers, body if applicable)
5. Send to `http://localhost:5082/predict` (or `MLSEC_API_URL` env var)
6. Return `{payload, http_request, prediction, probability, detected}`

**Output:** `AttackResult(payload, http_request, prediction, probability, threshold_used, detected)`

---

### ReporterAgent

**Role:** `Security Operations Analyst`
**Goal:** Aggregate attack simulation results and generate actionable reports for the blue team
**Backstory:** You are a security analyst who translates raw red team findings into executive-level reports. You focus on actionable intelligence: what failed to detect, why it matters, and what the blue team should prioritize.

**Available tools:**
- `FileWrite` — write reports
- `HttpRequest` — send alerts to webhooks

**Input:** List of `AttackResult`
**Process:**
1. Calculate `detection_rate = detected / total`
2. Filter FNs (detected=False)
3. If `fn_count > FN_THRESHOLD` (default: 3) → send ALERT
4. Generate FN Report in markdown
5. Save trending data (historical detection_rate)

**Output:** `FNReport(timestamp, total_payloads, detection_rate, fn_list, alert_triggered)`

---

## Threshold and Alerting

### FN_THRESHOLD

Default: **3 FNs in a session** = alert triggered

This threshold is configurable via `RT_FN_THRESHOLD` env var.

### Alert destinations

| Destination | Trigger | Format |
|---|---|---|
| Local file | Always | `reports/red_team_fn_{timestamp}.md` |
| Slack webhook | `alert_triggered=True` | Block kit message |
| Airflow DAG trigger | `alert_triggered=True` | DAG `dag_red_team_alert` |

### FN Report structure

```markdown
# Red Team FN Report
Generated: 2026-04-21T14:30:00Z

## Summary
| Metric | Value |
|---|---|
| Total tested payloads | 47 |
| Detected | 44 |
| Not detected (FN) | 3 |
| Detection rate | 93.6% |

## False Negatives

### 1. SQL Injection — boolean-based blind
- **Payload:** `' OR (SELECT 1 FROM users WHERE id=1)=1 --`
- **Source:** https://www.exploit-db.com/exploits/51234
- **Category:** SQLi
- **Prediction:** 0 (not detected)
- **Probability:** 0.12
- **HTTP Request:** `GET /login?id='+OR+(SELECT+1)...`

### 2. XSS — polyglot
...
```

---

## Scope

### In scope

- Automated monitoring of public payload sources
- Testing against Model A (HTTP web attacks)
- FN reporting with alert threshold
- Integration with existing MLOps/Blue Team workflow

### Out of scope (MVP)

- **Model B** (Network Attack Detection) — same framework, different input type
- **Payload generation** — only external sources are consumed (no attack gen)
- **Active exploitation** — only tested against API (not sent to external systems)
- **Persistence** — tested payloads are not stored long-term (only logged)
- **UI/Dashboard** — reports in markdown + files, no dedicated frontend

### Out of scope (post-MVP)

- SIEM integration (splunk, elastic)
- Re-training automation based on FN reports
- Manual Red Team (real coordinated pentests)

---

## Airflow Integration

### DAG: `dag_red_team_agent`

Trigger: scheduled (default: every 6h) or manual

```
schedule: "0 */6 * * *"  # every 6 hours
```

**Tasks:**

| Task | What it does | Script |
|---|---|---|
| `hunt_payloads` | PayloadHunterAgent searches sources | `crewai_pipeline.py` |
| `simulate_attacks` | AttackSimulatorAgent tests each payload | `crewai_pipeline.py` |
| `generate_report` | ReporterAgent compiles FN report | `crewai_pipeline.py` |
| `send_alert` | Sends alert to Slack if threshold exceeded | `send_alert.py` |

### Context variables (Airflow)

```python
RT_FN_THRESHOLD = Variable.get("rt_fn_threshold", default_var=3)
RT_API_URL = Variable.get("rt_api_url", default_var="http://api:5082/predict")
RT_REPORT_DIR = Variable.get("rt_report_dir", default_var="/opt/airflow/data/reports")
RT_SLACK_WEBHOOK = Variable.get("rt_slack_webhook", default_var=None)
```

---

## Success Metrics

| Metric | Target | Who measures it |
|---|---|---|
| `detection_rate_fresh` | ≥ 85% | Red Team Agent |
| Generated FN report | every cycle | Red Team Agent |
| Alert if FN > threshold | 100% (if condition met) | Red Team Agent |
| Full cycle latency | < 10 min | Airflow |
| Source coverage | all configured | Ops |

### MLflow Tracking

The Red Team Agent can log metrics in a `red-team` MLflow experiment:

| Metric | Description |
|---|---|
| `fresh_detection_rate` | % of fresh payloads detected |
| `fn_count` | Amount of FNs in the cycle |
| `payloads_tested` | Total processed payloads |
| `sources_queried` | Amount of queried sources |
| `execution_time_s` | Total cycle time |

---

## Tech Stack

| Tool | Role |
|---|---|
| **CrewAI** | Agent orchestration framework |
| **Apache Airflow** | Scheduler + DAG orchestration |
| **FastAPI** | Inference API (testing target) |
| **MLflow** | Agent metrics tracking |
| **Python 3.11** | Language |

---

## Project Files

```
PMT MLSec/
├── crewai/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── payload_hunter.py
│   │   ├── attack_simulator.py
│   │   └── reporter.py
│   ├── crew/
│   │   ├── __init__.py
│   │   └── red_team_crew.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── http_attack_tool.py
│   │   ├── url_encoder.py
│   │   └── webhook_alert.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   └── run_agent.py
│   └── requirements_crewai.txt
├── dags/
│   └── dag_red_team_agent.py
├── reports/
│   └── .gitkeep  # generated FN reports
└── docs/
    └── red_team_agent.md  # this document
```

---

## Roadmap — Implementation Phases

### Phase R1 — Core Agent (MVP)

**Goal:** Functional agent that tests against API and generates FN reports

**Deliverables:**
- [ ] `requirements_crewai.txt`
- [ ] 3 basic agents (PayloadHunter, AttackSimulator, Reporter)
- [ ] HTTP attack tool (`http_attack_tool.py`)
- [ ] URL encoding tool (`url_encoder.py`)
- [ ] Basic pipeline `crewai_pipeline.py`
- [ ] FN report in markdown
- [ ] `dag_red_team_agent.py` DAG scheduled every 6h
- [ ] Documentation

**Definition of done:** The crew runs end-to-end and generates an FN report with at least 1 tested payload

### Phase R2 — Alerting + Integration

**Goal:** FN reports reach Blue Team + MLOps

**Deliverables:**
- [ ] Webhook alert tool (`webhook_alert.py`)
- [ ] Slack integration (configurable webhook)
- [ ] Metrics in MLflow (`red-team` experiment)
- [ ] Configurable threshold via env vars / Airflow vars
- [ ] FN report includes full HTTP request for reproduction

**Definition of done:** Blue Team receives Slack alert when FN > threshold

### Phase R3 — Multi-source + Deduplication

**Goal:** Full source coverage with intelligent filtering

**Deliverables:**
- [ ] GitHub API integration for PayloadAllTheThings
- [ ] NVD CVE feed integration
- [ ] Payload deduplication (hash-based in last 24h)
- [ ] Category filtering (only HTTP-related)
- [ ] Source fallback if one fails

**Definition of done:** 5+ configured sources, FN report shows source for each payload

### Phase R4 — Advanced + Model B

**Status:** Backlog

**Potential deliverables:**
- [ ] Model B extension (network attacks)
- [ ] SIEM Integration (Splunk/Elastic)
- [ ] Historical detection_rate trend analysis
- [ ] Auto-trigger re-training when detection_rate < 80%

---

## Open Questions

1. **Initial scheduling?** Proposal: every 6h (R1), adjust to every 1h or daily post-R2
2. **Initial sources?** Start with Exploit-DB + PayloadAllTheThings (GitHub raw)
3. **Where are FN reports saved?** `data/reports/red_team/` on host, mounted in container
4. **Slack or email for alerts?** The document uses Slack as example, but it is configurable
5. **Is the tested payloads dataset persisted?** Not in MVP — only MLflow logs
6. **Does the Red Team Agent need API credentials?** Only the public `/predict` endpoint — no auth required

---

## References

- [Red Team — Practical Guide](red_team/index.md)
- [MLOps + AIOps + Blue Team workflow](mlops_aiops_blue_team.md)
- [Model Registry — deployment stages](model_registry.md)
- [Inference API](api.md)
- [Airflow setup](airflow.md)
- [CrewAI documentation](https://docs.crewai.com/)
