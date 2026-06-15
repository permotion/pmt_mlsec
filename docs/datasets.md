# Datasets

## Conventions

- Files in `data/raw/` **are never modified** — they are the source of truth
- Each dataset has: data file(s), `README.md`, `LICENSE`, SHA-256 hash
- Processing reads from `raw/` and writes to `processed/`
- Unified labels: `0` = benign/normal · `1` = malicious/attack

---

## Dataset A — CSIC 2010

**Model:** Web Attack Detection

| Field | Value |
|---|---|
| Name | HTTP CSIC 2010 |
| Source | CSIC (Spanish National Research Council) |
| Type | HTTP requests (GET/POST) |
| Classes | Normal / Anomalous (attacks) |
| Size | ~36,000 normal requests, ~25,000 attacks |
| Format | Plain text (Raw HTTP) |
| License | For research use |

**Included attack types:**
SQL Injection, Buffer Overflow, Information Gathering, Files Disclosure,
CRLF Injection, XSS, Parameter Tampering, CSRF

**Local path:**
```
data/raw/csic2010/
├── csic_database.csv          ← full dataset (61,065 records, 0/1 labels)
├── README.md
└── CHECKSUMS.sha256
```

**Note:** The Kaggle version is a pre-processed CSV. The original comes in
raw HTTP .txt files separated by train/test splits.

**SHA-256:**
```
c420f0bc0464376de75b6c419a0ac226fe69fe12c8ac4908843273721e44e637  csic_database.csv
```

**How to download:**
```bash
# Original source — requires request form:
# http://www.isi.csic.es/dataset/
# Alternative: search Kaggle for "CSIC 2010 HTTP dataset"
```

---

## Dataset B — UNSW-NB15

**Model:** Network Attack Detection

| Field | Value |
|---|---|
| Name | UNSW-NB15 |
| Source | University of New South Wales, Canberra |
| Type | Network flow features (CSV) |
| Classes | Normal / 9 attack categories |
| Size | ~2.5M records (~257MB CSV) |
| Format | CSV with 49 features |
| License | For research use |

**Attack categories:**
Fuzzers, Analysis, Backdoors, DoS, Exploits, Generic, Reconnaissance, Shellcode, Worms

**Key features:**
`dur`, `proto`, `service`, `state`, `spkts`, `dpkts`, `sbytes`, `dbytes`,
`rate`, `sttl`, `dttl`, `sload`, `dload`, `ct_srv_src`, `label`

**Local path:**
```
data/raw/unsw_nb15/
├── UNSW_NB15_training-set.parquet   ← 175,341 records
├── UNSW_NB15_testing-set.parquet    ← 82,332 records
├── README.md
└── CHECKSUMS.sha256
```

**Note:** The Kaggle version (dhoogla/unswnb15) comes in Parquet format
with official train/test split and 36 columns (35 features + label). Labels in `0/1`.

**SHA-256:**
```
f6989e65032e75770f37a5fa64d1d556effd6ac6240c99b0ab4df73b490c1918  UNSW_NB15_training-set.parquet
a0270aeb2219aaa686551cdf6d4f94c4478b69f819225176149606cd1492d5e1  UNSW_NB15_testing-set.parquet
```

**How to download:**
```bash
# Official source:
# https://research.unsw.edu.au/projects/unsw-nb15-dataset
# Also available on Kaggle: "UNSW-NB15"
```

---

## Ingestion checklist

Before considering a dataset ingestion complete:

- [ ] Files downloaded to `data/raw/{dataset}/`
- [ ] SHA-256 hash calculated and saved in `CHECKSUMS.sha256`
- [ ] `README.md` with source, download date, and license
- [ ] This page updated with verified hash
- [ ] Dataset accessible from EDA notebook
