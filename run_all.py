"""
Home by Home Plan — Full Pipeline Runner
=========================================
Royal Borough of Greenwich · DG Cities

HOW TO USE:
  python run_all.py

ADDING NEW REPAIR DATA:
  1. Drop the new file into the Repairs folder
  2. Add it to REPAIR_FILES below
  3. Set REBUILD_CACHE = True
  4. Run the script
"""

import os, sys, time
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ── Set to True when source data has changed, False for fast rerun ──────────
REBUILD_CACHE = True

# ── All paths ────────────────────────────────────────────────────────────────
BASE         = r'G:\Shared drives\DG Cities\Projects\HomeByHomePlatform\HTML_Prototype'

MASTER_FILE    = BASE + r'\Data\Stock\HbH_Stock_Master_1.xlsx'
KEYSTONE_REP   = BASE + r'\Data\Keystone\Keystone Whole Stock Data - REP.xlsx'
KEYSTONE_ATT   = BASE + r'\Data\Keystone\Keystone Whole Stock Data - ATT.xlsx'
OUTPUT_FILE    = BASE + r'\Output\HbH_RAG_Scores.xlsx'
CACHE_REP      = BASE + r'\Data\Cache\cache_rep.parquet'
CACHE_ATT_DAMP = BASE + r'\Data\Cache\cache_att_damp.parquet'
CACHE_REPAIRS  = BASE + r'\Data\Cache\cache_repairs.parquet'
PROP_OUT       = BASE + r'\Data\Cache\prop_out.parquet'
AG_OUT         = BASE + r'\Data\Cache\ag_out.parquet'
SCRIPTS_DIR    = BASE + r'\Scripts'

# Create cache folder if it doesn't exist
os.makedirs(BASE + r'\Data\Cache', exist_ok=True)

# ── Repair files ──────────────────────────────────────────────────────────────
R = BASE + r'\Data\Repairs'

REPAIR_FILES = [
    # 2023/24 Q1-Q3 (quarterly .xls files)
    {'path': R + r'\2023-24_Q1.xls',          'engine': 'xlrd',     'header': 1},
    {'path': R + r'\2023-24_Q2.xls',          'engine': 'xlrd',     'header': 1},
    {'path': R + r'\2023-24_Q3.xls',          'engine': 'xlrd',     'header': 1},
    # 2023/24 Q4: extracted from full year file (Jan-Mar 2024 only)
    {'path': R + r'\2023-24.xlsx',             'engine': 'openpyxl', 'header': 0,
     'date_filter_from': '2024-01-01', 'date_filter_to': '2024-03-31'},
    # 2024/25
    {'path': R + r'\2024-25_Q1 1.xlsx',       'engine': 'openpyxl', 'header': 0},
    {'path': R + r'\2024-25_Q2.xlsx',         'engine': 'openpyxl', 'header': 0},
    {'path': R + r'\2024-25_Q3 1.xlsx',       'engine': 'openpyxl', 'header': 0},
    {'path': R + r'\2024-25_Q4_to10Mar.xls',  'engine': 'xlrd',     'header': 1},
    # 2025/26
    {'path': R + r'\2025-26_Q1 2.xls',        'engine': 'xlrd',     'header': 1},
    {'path': R + r'\2025-26_Q2 1.xls',        'engine': 'xlrd',     'header': 1},
    {'path': R + r'\2025-26_Q3 1.xls',        'engine': 'xlrd',     'header': 1},
    {'path': R + r'\2025-26_Q4 1.xls',        'engine': 'xlrd',     'header': 1},
    # Add new quarters here, e.g.:
    # {'path': R + r'\2026-27_Q1.xlsx', 'engine': 'openpyxl', 'header': 0},
]

REPAIR_DATE_FROM = pd.Timestamp('2023-04-01')
REPAIR_DATE_TO   = pd.Timestamp('2026-03-31')

# ── Helpers ───────────────────────────────────────────────────────────────────
def banner(msg):
    print(f'\n{"="*60}\n  {msg}\n{"="*60}')

# ── Step 0: Check files exist ─────────────────────────────────────────────────
banner('STEP 0 — Checking input files')
errors = []
for label, path in [
    ('Stock Master', MASTER_FILE),
    ('Keystone REP', KEYSTONE_REP),
    ('Keystone ATT', KEYSTONE_ATT),
]:
    if os.path.exists(path):
        print(f'  OK   {label}')
    else:
        print(f'  MISSING  {label}')
        print(f'           {path}')
        errors.append(path)

available = []
for f in REPAIR_FILES:
    name = os.path.basename(f['path'])
    if os.path.exists(f['path']):
        print(f'  OK   {name}')
        available.append(f)
    else:
        print(f'  MISSING  {name}')

if errors:
    print(f'\nABORTED — {len(errors)} required file(s) missing. Check paths above.')
    sys.exit(1)

if len(available) < len(REPAIR_FILES):
    missing = len(REPAIR_FILES) - len(available)
    print(f'\nWARNING — {missing} repair file(s) missing, continuing with the rest.')

# ── Step 1: Build cache ───────────────────────────────────────────────────────
if REBUILD_CACHE:

    banner('STEP 1a — Caching Keystone REP')
    t = time.time()
    df = pd.read_excel(KEYSTONE_REP, sheet_name='SurveyRepairs', header=0, dtype=str)
    df = df.iloc[2:].reset_index(drop=True)
    df.to_parquet(CACHE_REP, index=False)
    print(f'  REP cached: {len(df):,} rows  ({time.time()-t:.0f}s)')

    banner('STEP 1b — Caching Keystone ATT (damp only)')
    t = time.time()
    df2 = pd.read_excel(KEYSTONE_ATT, sheet_name='SurveyAttributes', header=0, dtype=str)
    df2 = df2.iloc[2:].reset_index(drop=True)
    damp = df2[df2['Component'].str.contains('Damp and Mould', na=False)].copy()
    damp.to_parquet(CACHE_ATT_DAMP, index=False)
    print(f'  ATT damp cached: {len(damp):,} rows  ({time.time()-t:.0f}s)')

    banner('STEP 1c — Caching repairs')
    t = time.time()
    dfs = []
    for f in available:
        df = pd.read_excel(f['path'], engine=f['engine'], header=f['header'])
        df = df.dropna(subset=['50_Property_Ref', '13_Works_Order_Description'])
        if 'WOR Raised' in df.columns:
            df['_date'] = pd.to_datetime(df['WOR Raised'], errors='coerce')
        elif '17_Issued_Date' in df.columns:
            df['_date'] = pd.to_datetime(df['17_Issued_Date'], errors='coerce')
        else:
            df['_date'] = pd.NaT
        if 'WPR_Code' not in df.columns:
            df['WPR_Code'] = None
        # Extract cost column if available
        cost_col = '14_Total_Cost_Now'
        df['_cost'] = pd.to_numeric(df[cost_col], errors='coerce').fillna(0) if cost_col in df.columns else 0.0
        subset = df[['50_Property_Ref','13_Works_Order_Description','WPR_Code','_date','_cost']].copy()
        subset['_date'] = pd.to_datetime(df['_date'], errors='coerce')
        # Apply date filter where specified (used for Q4 extraction from full year file)
        if 'date_filter_from' in f:
            subset = subset[
                (subset['_date'] >= pd.Timestamp(f['date_filter_from'])) &
                (subset['_date'] <= pd.Timestamp(f['date_filter_to']))
            ]
        dates = subset['_date'].dropna()
        name  = os.path.basename(f['path'])
        tag   = f" [Q4 only]" if 'date_filter_from' in f else ''
        print(f'  {name}{tag}: {len(subset):,} rows'
              + (f'  {dates.min().date()} to {dates.max().date()}' if len(dates) > 0 else ''))
        dfs.append(subset.astype(str).assign(_date=subset['_date']))

    df_all = pd.concat(dfs, ignore_index=True)
    df_all['_date'] = pd.to_datetime(df_all['_date'], errors='coerce')
    df_all = df_all[
        (df_all['_date'] >= REPAIR_DATE_FROM) &
        (df_all['_date'] <= REPAIR_DATE_TO)
    ]
    # Deduplicate: same property + description + date + cost = same work order
    # Different SOR codes on same WO generate duplicate rows - keep one
    df_all = df_all.drop_duplicates(
        subset=['50_Property_Ref','13_Works_Order_Description','_date','_cost'])
    df_all.to_parquet(CACHE_REPAIRS, index=False)
    print(f'\n  Total: {len(df_all):,} rows across {df_all["50_Property_Ref"].nunique():,} properties  ({time.time()-t:.0f}s)')
    print(f'  Date range: {df_all["_date"].min().date()} to {df_all["_date"].max().date()}')
    for fy, s, e in [('2023/24','2023-04-01','2024-03-31'),
                      ('2024/25','2024-04-01','2025-03-31'),
                      ('2025/26','2025-04-01','2026-03-31')]:
        n = ((df_all['_date'] >= s) & (df_all['_date'] <= e)).sum()
        print(f'    {fy}: {n:,} rows')

else:
    banner('STEP 1 — Skipping cache rebuild (REBUILD_CACHE = False)')

# ── Step 2: RAG scoring ───────────────────────────────────────────────────────
banner('STEP 2 — Running RAG scoring engine')
t = time.time()

rag_script = os.path.join(SCRIPTS_DIR, 'rag_scoring.py')
with open(rag_script, 'r', encoding='utf-8') as f:
    code = f.read()

# Inject correct paths into the scoring script
path_overrides = f"""
MASTER_FILE    = r'{MASTER_FILE}'
OUTPUT_FILE    = r'{OUTPUT_FILE}'
CACHE_REP      = r'{CACHE_REP}'
CACHE_ATT_DAMP = r'{CACHE_ATT_DAMP}'
CACHE_REPAIRS  = r'{CACHE_REPAIRS}'
KEYSTONE_REP   = r'{KEYSTONE_REP}'
KEYSTONE_ATT   = r'{KEYSTONE_ATT}'
"""
insert_at = code.find('# ── Component')
code = code[:insert_at] + path_overrides + '\n' + code[insert_at:]
exec(compile(code, rag_script, 'exec'), {'__file__': rag_script})
print(f'\n  Scoring complete  ({time.time()-t:.0f}s)')

# ── Step 3: Build enriched repair counts ─────────────────────────────────────
banner('STEP 3 — Building enriched repair counts')
t = time.time()

master  = pd.read_excel(MASTER_FILE, dtype=str)
df_ag   = pd.read_excel(OUTPUT_FILE, sheet_name='Asset Group RAG')
df_damp = pd.read_excel(OUTPUT_FILE, sheet_name='Damp & Mould Assessment')
df_prop = pd.read_excel(OUTPUT_FILE, sheet_name='Property RAG', dtype=str)

master['_key'] = master['Property Ref (UPRN)'].str.strip().str.lstrip('0')
key_to_ag = master.set_index('_key')['Asset Group'].to_dict()

df_repairs = pd.read_parquet(CACHE_REPAIRS)
df_repairs['_key']  = df_repairs['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
df_repairs['_date'] = pd.to_datetime(df_repairs['_date'], errors='coerce')
df_repairs['Asset Group'] = df_repairs['_key'].map(key_to_ag)

def fy(d):
    if pd.isna(d): return None
    return f'{d.year-1}/{str(d.year)[2:]}' if d.month < 4 else f'{d.year}/{str(d.year+1)[2:]}'
df_repairs['FY'] = df_repairs['_date'].apply(fy)

WPR_MAP = {
    'GSW':'communal_heating','GRW':'communal_heating','CPH':'communal_heating',
    'DPC':'damp_mould','DPR':'damp_mould','PSO':'damp_mould',
    'MRC':'bathroom','EHC':'electrical','DIS':'window',
}
KEYWORD_RULES = [
    (['roof','roofing','flat roof','pitched roof','felt','fascia','soffit',
      'gutter','downpipe','chimney','flashing'], 'roof'),
    (['rewire','wiring','electrical','electric','socket','fuse',
      'consumer unit','light fitting','eicr'], 'electrical'),
    (['boiler','heating','radiator','gas','co alarm','heat pump',
      'thermostat','pipework'], 'communal_heating'),
    (['damp','mould','mold','condensation','moisture','damp proof',
      'mould wash','anti-mould'], 'damp_mould'),
    (['kitchen','cupboard','worktop','sink unit','cooker','hob',
      'kitchen floor','kitchen units'], 'kitchen'),
    (['bathroom','bath','shower','toilet','wc ','wet room','basin',
      'sanitary','bath panel'], 'bathroom'),
    (['window','glazing','double glaz','dgu','upvc window',
      'window frame','window seal'], 'window'),
    (['door','front door','back door','entrance door','fire door',
      'door frame','lock','letterbox'], 'door'),
]
def cat(wpr, desc):
    if pd.notna(wpr) and str(wpr) in WPR_MAP: return WPR_MAP[str(wpr)]
    d = str(desc).lower() if pd.notna(desc) else ''
    for kws, c in KEYWORD_RULES:
        if any(k in d for k in kws): return c
    return 'other'

# ── LLM categories (if cache exists) ─────────────────────────────────────────
LLM_CACHE = BASE + r'\Data\Cache\llm_categories.parquet'

LLM_TO_RAG_CAT = {
    'Leak':             'damp_mould',
    'Damp':             'damp_mould',
    'Electrical':       'electrical',
    'Plumbing':         'bathroom',
    'Door/Window':      'window',
    'Heating/Hot Water':'communal_heating',
    'Roof':             'roof',
    'Structural/Wall':  'roof',
    'Kitchen':          'kitchen',
    'Bathroom':         'bathroom',
    'Accessibility':    'other',
    'Asbestos':         'other',
    'Fence/Garden':     'other',
    'Pest Control':     'other',
    'Vacancy':          'other',
    'Other':            'other',
}

USE_LLM = False
if os.path.exists(LLM_CACHE):
    try:
        df_llm = pd.read_parquet(LLM_CACHE)
        llm_lookup = df_llm.set_index('description')[
            ['llm_category','llm_scale','llm_leak_cause','llm_leak_impact']
        ].to_dict('index')
        df_repairs['desc_clean'] = df_repairs['13_Works_Order_Description'].astype(str).str.strip()
        df_repairs['llm_category']    = df_repairs['desc_clean'].map(
            lambda x: llm_lookup.get(x, {}).get('llm_category'))
        df_repairs['llm_scale']        = df_repairs['desc_clean'].map(
            lambda x: llm_lookup.get(x, {}).get('llm_scale'))
        df_repairs['llm_leak_cause']   = df_repairs['desc_clean'].map(
            lambda x: llm_lookup.get(x, {}).get('llm_leak_cause'))
        df_repairs['llm_leak_impact']  = df_repairs['desc_clean'].map(
            lambda x: llm_lookup.get(x, {}).get('llm_leak_impact'))
        n_enriched = df_repairs['llm_category'].notna().sum()
        print(f'  LLM categories applied: {n_enriched:,} of {len(df_repairs):,} repairs '
              f'({n_enriched/len(df_repairs)*100:.1f}%)')
        USE_LLM = True
    except Exception as e:
        print(f'  WARNING: Could not load LLM cache: {e} — using keyword fallback')

# Category assignment — LLM first, keyword fallback
def cat(wpr, desc, llm_cat=None):
    # Use LLM category if available
    if USE_LLM and pd.notna(llm_cat) and llm_cat:
        mapped = LLM_TO_RAG_CAT.get(str(llm_cat), 'other')
        if mapped != 'other':
            return mapped
    # WPR code fallback
    if pd.notna(wpr) and str(wpr) in WPR_MAP: return WPR_MAP[str(wpr)]
    # Keyword fallback
    d = str(desc).lower() if pd.notna(desc) else ''
    for kws, c in KEYWORD_RULES:
        if any(k in d for k in kws): return c
    return 'other'

df_repairs['Category'] = df_repairs.apply(
    lambda r: cat(r['WPR_Code'], r['13_Works_Order_Description'],
                  r.get('llm_category') if USE_LLM else None), axis=1)

FY_LIST = ['2023/24','2024/25','2025/26']
CATS    = ['roof','door','window','kitchen','bathroom','damp_mould']

# Property-level FY counts
prop_fy = (df_repairs[df_repairs['FY'].isin(FY_LIST) & df_repairs['Category'].isin(CATS)]
           .groupby(['_key','Category','FY']).size().reset_index(name='count'))
prop_pivot = prop_fy.pivot_table(
    index='_key', columns=['Category','FY'], values='count', fill_value=0)
prop_pivot.columns = [f'{c}_{f}' for c, f in prop_pivot.columns]
prop_pivot = prop_pivot.reset_index()
for c in CATS:
    fy_cols = [col for col in prop_pivot.columns if col.startswith(f'{c}_')]
    prop_pivot[f'{c}_3yr_total'] = prop_pivot[fy_cols].sum(axis=1)

# AG-level FY counts
ag_fy = (df_repairs[df_repairs['FY'].isin(FY_LIST) & df_repairs['Category'].isin(CATS)]
         .groupby(['Asset Group','Category','FY']).size().reset_index(name='count'))
ag_pivot = ag_fy.pivot_table(
    index='Asset Group', columns=['Category','FY'], values='count', fill_value=0).reset_index()
ag_pivot.columns = ['Asset Group'] + [f'{c}_{f}' for c, f in ag_pivot.columns[1:]]

# Surveyor damp notes from REP cache
df_rep = pd.read_parquet(CACHE_REP)
df_rep['_key'] = df_rep['UPRN'].str.strip().str.lstrip('0')

def is_damp(n):
    n = str(n).lower() if pd.notna(n) else ''
    if not any(kw in n for kw in ['damp','mould','mold','condensation','penetrating','rising damp']): return False
    if 'wet system' in n and 'damp' not in n and 'mould' not in n: return False
    return True

def sev(n):
    n = str(n).lower() if pd.notna(n) else ''
    if any(w in n for w in ['severe','significant','major','extensive']): return 'Severe'
    if any(w in n for w in ['moderate','present','issues present?=yes']): return 'Moderate'
    if any(w in n for w in ['slight','minor']): return 'Slight'
    if 'issues present?=no' in n: return 'None'
    return 'Mentioned'

def cons(n):
    n = str(n).lower() if pd.notna(n) else ''
    if 'martin arnold' in n: return 'Martin Arnold'
    if 'potter raper' in n: return 'Potter Raper'
    if 'fft' in n: return 'FFT'
    return 'Other'

df_rep['genuine_damp'] = df_rep['Notes'].apply(is_damp)
dm = df_rep[df_rep['genuine_damp']].copy()
dm['Sev']  = dm['Notes'].apply(sev)
dm['Cons'] = dm['Notes'].apply(cons)
srank = {'Severe':4,'Moderate':3,'Slight':2,'Mentioned':1,'None':0}
dm['_r'] = dm['Sev'].map(srank).fillna(0)
surv_damp = (dm.sort_values('_r', ascending=False)
               .groupby('_key').first().reset_index()
               [['_key','Sev','Cons','Notes','Component']]
               .rename(columns={'Sev':'Surveyor_Damp_Severity',
                                'Cons':'Surveyor_Damp_Consultant',
                                'Notes':'Surveyor_Damp_Note',
                                'Component':'Surveyor_Damp_Component'}))
surv_damp['Surveyor_Damp_Note'] = surv_damp['Surveyor_Damp_Note'].str[:300]

# Merge everything onto property sheet
df_prop['_key'] = df_prop['Property Ref (UPRN)'].str.strip().str.lstrip('0')
df_detail = (df_prop.merge(prop_pivot, on='_key', how='left')
                    .merge(surv_damp,  on='_key', how='left'))
count_cols = [c for c in df_detail.columns
              if any(cat in c for cat in CATS)
              and ('2023' in c or '2024' in c or '2025' in c or '3yr' in c)]
df_detail[count_cols] = df_detail[count_cols].fillna(0).astype(int)

# AG full merge
df_ag_full = (df_ag.merge(ag_pivot, on='Asset Group', how='left')
                   .merge(df_damp,  on='Asset Group', how='left', suffixes=('','_damp')))
df_ag_full = df_ag_full.drop(columns=[c for c in df_ag_full.columns if c.endswith('_damp')])

# Build final property output column list
rag_cols  = [c for c in df_detail.columns if c.startswith('RAG_')]
base_cols = ['Property Ref (UPRN)','Address','Postcode','Ward','Asset Group',
             'Estate','Ownership Type','EPC Rating','ATT_Severity',
             'Surveyor_Damp_Severity','Surveyor_Damp_Consultant',
             'Surveyor_Damp_Component','Surveyor_Damp_Note','Damp_Repair_Count']
repair_cols = []
for c in CATS:
    for f in FY_LIST:
        col = f'{c}_{f}'
        if col in df_detail.columns: repair_cols.append(col)
    if f'{c}_3yr_total' in df_detail.columns: repair_cols.append(f'{c}_3yr_total')
all_cols = [c for c in base_cols + rag_cols + repair_cols if c in df_detail.columns]

df_detail[all_cols].to_parquet(PROP_OUT, index=False)
df_ag_full.to_parquet(AG_OUT, index=False)
print(f'  Property RAG: {len(df_detail):,} rows x {len(all_cols)} cols  ({time.time()-t:.0f}s)')

# ── Step 4: Format Excel ──────────────────────────────────────────────────────
banner('STEP 4 — Formatting Excel output')
t = time.time()

fmt_script = os.path.join(SCRIPTS_DIR, 'format_output.py')
with open(fmt_script, 'r', encoding='utf-8') as f:
    code = f.read()

path_overrides = f"""
PROP_OUT = r'{PROP_OUT}'
AG_OUT   = r'{AG_OUT}'
OUTPUT   = r'{OUTPUT_FILE}'
"""
code = path_overrides + code
exec(compile(code, fmt_script, 'exec'), {'__file__': fmt_script})
print(f'  Formatting complete  ({time.time()-t:.0f}s)')

# ── Done ──────────────────────────────────────────────────────────────────────
banner('ALL DONE')
print(f'  Output saved to: {OUTPUT_FILE}')
print(f'\n  To add a new quarter:')
print(f'  1. Drop the file into: {R}')
print(f'  2. Add it to REPAIR_FILES near the top of this script')
print(f'  3. Set REBUILD_CACHE = True and run again')
