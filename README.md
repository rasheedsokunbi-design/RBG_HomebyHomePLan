# Home by Home Plan — Intelligence Portal
**Royal Borough of Greenwich · DG Cities**

An interactive HTML intelligence portal for RBG housing stock, built from Keystone REP survey data, reactive repairs history, stock master EPC/SAP data and compliance records.

---

## Files in this repository

| File | Purpose |
|------|---------|
| `run_all.py` | **Run first.** Loads all repair files, applies LLM categories, runs RAG scoring. Outputs `HbH_RAG_Scores.xlsx` and cache files. |
| `run_llm_categoriser.py` | One-off script to categorise repair descriptions using GPT. Only needs running when new repair quarters are added. Requires an OpenAI API key. |
| `build_portal.py` | **Run second.** Reads RAG scores and cache files, injects all data into the template, and produces the final `HbH_Portal.html`. |
| `HbH_Portal_template.html` | The portal template — contains all HTML, CSS and JavaScript. Edit this file to change the portal layout, styling or page content. |

---

## How to run

### Prerequisites
- Python 3.12
- Required packages: `pandas`, `openpyxl`, `pyarrow`, `xlrd`
- Access to the shared Google Drive: `G:\Shared drives\DG Cities\Projects\HomeByHomePlatform\HTML_Prototype\`

### Step 1 — Build the data cache
Only needed when adding new repair quarters or running for the first time. Set `REBUILD_CACHE = True` at the top of `run_all.py`, then:

```powershell
& "C:\Users\...\Python312\python.exe" "...\Scripts\run_all.py"
```

Set `REBUILD_CACHE = False` again afterwards so future runs are faster.

### Step 2 — Build the portal
```powershell
& "C:\Users\...\Python312\python.exe" "...\Scripts\build_portal.py"
```

This produces `Portal\HbH_Portal.html`. Open in Chrome to view.

### Step 3 — Adding a new repair quarter
1. Drop the new `.xls` or `.xlsx` file into `Data\Repairs\`
2. Add it to `REPAIR_FILES` near the top of `run_all.py`
3. Set `REBUILD_CACHE = True` and run `run_all.py`
4. Run `run_llm_categoriser.py` if new repair descriptions need categorising (requires OpenAI API key)
5. Run `build_portal.py`

---

## Data folder structure (on shared drive, not in this repo)

```
HTML_Prototype\
├── Data\
│   ├── Stock\          — HbH_Stock_Master_1.xlsx
│   ├── Keystone\       — REP and ATT survey exports
│   ├── Repairs\        — Quarterly repair files (12 files, 2023/24–2025/26)
│   ├── Costs\          — HbH_Component_Costs.xlsx
│   └── Cache\          — Auto-generated cache files (do not edit)
├── Output\             — HbH_RAG_Scores.xlsx
├── Portal\             — HbH_Portal.html (built output)
└── Scripts\            — Python scripts (mirrored in this repo)
```

---

## Portal pages

| # | Page | Description |
|---|------|-------------|
| 1 | Overview | KPIs, repair cost breakdown by asset group and category |
| 2 | Damp & Mould | Asset group risk ranking, leak analysis, LLM narrative summaries, property drill-down |
| 3 | Stock Condition | Survey coverage and component Year Due dates |
| 4 | Block & Compliance | Communal component priority scores, BSR-registered blocks, statutory compliance |
| 5 | Retrofit & Sustainability | EPC distribution, SAP scores, retrofit priority scoring |
| 6 | Decent Homes | 4-criteria assessment, LAHS export, property-level failure detail |
| 7 | Programme Builder | 5-year capital programme with budget modelling and 2-year bundling logic |
