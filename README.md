# HackNation6

Challenge #5: Foundation Models for Women's Hormonal Health

## NHANES Reproductive Health (P_RHQ) analysis

`P_RHQ.xpt` is the [NHANES 2017–March 2020 Reproductive Health](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.htm) questionnaire (SAS XPORT). It covers menstrual history, pregnancy, infertility, and hormone use for female participants aged 12+.

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Place the file at `data/P_RHQ.xpt` (or pass any path):

```bash
# from your Downloads folder, or re-download from CDC:
# curl -L -o data/P_RHQ.xpt \
#   https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.xpt
cp ~/Downloads/P_RHQ.xpt data/P_RHQ.xpt
```

### Extract → CSV

```bash
python scripts/extract_xpt.py data/P_RHQ.xpt
# → outputs/P_RHQ.csv
# → outputs/P_RHQ_profile.csv
# → outputs/P_RHQ_data_dictionary.csv
```

### Analyse (PCOS-adjacent)

```bash
python scripts/analyze_rhq.py data/P_RHQ.xpt
# → outputs/P_RHQ_pcos_proxy_flags.csv
# → outputs/P_RHQ_analysis_summary.md
# → outputs/figures/*.png
```

### Important caveat

`RHQ031` asks whether the participant had **at least one period in the past 12 months** — it is an amenorrhea/presence question, **not** a measure of cycle regularity. True Rotterdam oligo/anovulation is not coded directly in this file.
