# Datasets

## Convenciones

- Los archivos en `data/raw/` **nunca se modifican** — son la fuente de verdad
- Cada dataset tiene: archivo(s) de datos, `README.md`, `LICENSE`, hash SHA-256
- El procesamiento lee de `raw/` y escribe en `processed/`
- Labels unificados: `0` = benign/normal · `1` = malicious/attack

---

## Dataset A — CSIC 2010

**Modelo:** Web Attack Detection

| Campo | Valor |
|---|---|
| Nombre | HTTP CSIC 2010 |
| Fuente | CSIC (Spanish National Research Council) |
| Tipo | HTTP requests (GET/POST) |
| Clases | Normal / Anomalous (attacks) |
| Tamaño | ~36.000 requests normales, ~25.000 ataques |
| Formato | Texto plano (HTTP raw) |
| Licencia | Para uso en investigación |

**Tipos de ataques incluidos:**
SQL Injection, Buffer Overflow, Information Gathering, Files Disclosure,
CRLF Injection, XSS, Parameter Tampering, CSRF

**Ubicación local:**
```
data/raw/csic2010/
├── csic_database.csv          ← dataset completo (61.065 registros, labels 0/1)
├── README.md
└── CHECKSUMS.sha256
```

**Nota:** La versión de Kaggle es un CSV pre-procesado. El original viene en
archivos .txt de HTTP raw separados por split train/test.

**SHA-256:**
```
c420f0bc0464376de75b6c419a0ac226fe69fe12c8ac4908843273721e44e637  csic_database.csv
```

**Cómo descargar:**
```bash
# Fuente original — requiere formulario de solicitud:
# http://www.isi.csic.es/dataset/
# Alternativa: buscar en Kaggle "CSIC 2010 HTTP dataset"
```

---

## Dataset B — UNSW-NB15

**Modelo:** Network Attack Detection

| Campo | Valor |
|---|---|
| Nombre | UNSW-NB15 |
| Fuente | University of New South Wales, Canberra |
| Tipo | Features de flujo de red (CSV) |
| Clases | Normal / 9 categorías de ataque |
| Tamaño | ~2.5M registros (~257MB CSV) |
| Formato | CSV con 49 features |
| Licencia | Para uso en investigación |

**Categorías de ataque:**
Fuzzers, Analysis, Backdoors, DoS, Exploits, Generic, Reconnaissance, Shellcode, Worms

**Features clave:**
`dur`, `proto`, `service`, `state`, `spkts`, `dpkts`, `sbytes`, `dbytes`,
`rate`, `sttl`, `dttl`, `sload`, `dload`, `ct_srv_src`, `label`

**Ubicación local:**
```
data/raw/unsw_nb15/
├── UNSW_NB15_training-set.parquet   ← 175.341 registros
├── UNSW_NB15_testing-set.parquet    ← 82.332 registros
├── README.md
└── CHECKSUMS.sha256
```

**Nota:** La versión de Kaggle (dhoogla/unswnb15) viene en formato Parquet
con split train/test oficial y 36 columnas (35 features + label). Labels en `0/1`.

**SHA-256:**
```
f6989e65032e75770f37a5fa64d1d556effd6ac6240c99b0ab4df73b490c1918  UNSW_NB15_training-set.parquet
a0270aeb2219aaa686551cdf6d4f94c4478b69f819225176149606cd1492d5e1  UNSW_NB15_testing-set.parquet
```

**Cómo descargar:**
```bash
# Fuente oficial:
# https://research.unsw.edu.au/projects/unsw-nb15-dataset
# También disponible en Kaggle: "UNSW-NB15"
```

---

## Checklist de ingesta

Antes de dar por completa la ingesta de un dataset:

- [ ] Archivos descargados en `data/raw/{dataset}/`
- [ ] Hash SHA-256 calculado y guardado en `CHECKSUMS.sha256`
- [ ] `README.md` con fuente, fecha de descarga y licencia
- [ ] Esta página actualizada con el hash verificado
- [ ] Dataset visible desde el notebook de EDA
