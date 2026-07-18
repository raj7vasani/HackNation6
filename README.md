# HackNation6

Challenge #5: Foundation Models for Women's Hormonal Health

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name=hacknation6 --display-name="HackNation6 (.venv)"
```

Put any SAS XPORT (`.xpt`) files in `data/`:

```bash
curl -L -o data/P_RHQ.xpt \
  https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.xpt
```

## Explore data (Jupyter)

General-purpose notebook — change `XPT_NAME` (or `XPT_PATH`) to analyse any file in `data/`.

Select kernel **HackNation6 (.venv)**, then:

```bash
source .venv/bin/activate
jupyter notebook notebooks/explore_xpt.ipynb
```
