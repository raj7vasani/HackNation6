# Place SAS XPORT (`.xpt`) files in this folder.

Example (NHANES Reproductive Health):

```bash
curl -L -o data/P_RHQ.xpt \
  https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.xpt
```

Then point the notebook at the file name (see `notebooks/explore_xpt.ipynb`).
