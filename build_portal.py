"""
Home by Home Plan — Portal Builder
=====================================
Royal Borough of Greenwich · DG Cities

Reads HbH_RAG_Scores.xlsx and cache files, builds data payloads,
and injects them into HbH_Portal_template.html to produce HbH_Portal.html.

Usage:
    python build_portal.py

Run this after run_all.py to update the portal with fresh data.
"""

import os, json, re, time
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ── PATHS ─────────────────────────────────────────────────────────────────────
BASE = r'G:\Shared drives\DG Cities\Projects\HomeByHomePlatform\HTML_Prototype'

MASTER_FILE    = BASE + r'\Data\Stock\HbH_Stock_Master_1.xlsx'
RAG_FILE       = BASE + r'\Output\HbH_RAG_Scores.xlsx'
TEMPLATE_FILE  = BASE + r'\Portal\HbH_Portal_template.html'
OUTPUT_FILE    = BASE + r'\Portal\HbH_Portal.html'
CACHE_REP      = BASE + r'\Data\Cache\cache_rep.parquet'
CACHE_REPAIRS  = BASE + r'\Data\Cache\cache_repairs.parquet'
# ─────────────────────────────────────────────────────────────────────────────

def banner(msg):
    print(f'\n{"="*60}\n  {msg}\n{"="*60}')

def inject(html, const_name, json_data):
    """
    Replace the value of a JavaScript const declaration.
    Finds 'const NAME = ' then replaces everything up to the next ;
    Works regardless of placeholder content or line endings.
    """
    # Handle both single-space and double-space variants
    for marker in [f'const {const_name}  = ', f'const {const_name} = ']:
        idx = html.find(marker)
        if idx >= 0:
            val_start = idx + len(marker)
            val_end   = html.find(';', val_start)
            if val_end >= 0:
                old_val = html[val_start:val_end]
                html = html[:val_start] + json_data + html[val_end:]
                print(f'  {const_name}: {len(old_val):,} chars -> {len(json_data):,} chars')
                return html
    print(f'  {const_name}: NOT FOUND in template')
    return html

# ── Step 1: Check files ───────────────────────────────────────────────────────
banner('STEP 1 — Checking files')

for label, path in [('Template',    TEMPLATE_FILE),
                     ('Stock Master', MASTER_FILE),
                     ('RAG Scores',   RAG_FILE)]:
    if os.path.exists(path):
        size = os.path.getsize(path) / 1024
        print(f'  OK   {label}: {size:.0f} KB')
    else:
        print(f'  MISSING  {label}: {path}')
        raise SystemExit(1)

for label, path in [('REP cache',     CACHE_REP),
                     ('Repairs cache', CACHE_REPAIRS)]:
    if os.path.exists(path):
        size = os.path.getsize(path) / 1024 / 1024
        print(f'  OK   {label}: {size:.0f} MB')
    else:
        print(f'  WARNING  {label} not found — some pages will have limited data')

# ── Step 2: Load data ─────────────────────────────────────────────────────────
banner('STEP 2 — Loading data')

master  = pd.read_excel(MASTER_FILE, dtype=str)
df_ag   = pd.read_excel(RAG_FILE, sheet_name='Asset Group RAG',         header=1)
df_damp = pd.read_excel(RAG_FILE, sheet_name='Damp & Mould Assessment', header=1)
df_prop = pd.read_excel(RAG_FILE, sheet_name='Property RAG',            header=1, dtype=str)

print(f'  Master:   {len(master):,} properties')
print(f'  AG RAG:   {len(df_ag):,} groups')
print(f'  Prop RAG: {len(df_prop):,} rows')

master['Latitude']  = pd.to_numeric(master['Latitude'],  errors='coerce')
master['Longitude'] = pd.to_numeric(master['Longitude'], errors='coerce')
master['_key']      = master['Property Ref (UPRN)'].str.strip().str.lstrip('0')

COMPONENTS = ['Roof', 'Door', 'Window', 'Kitchen', 'Bathroom', 'Damp_Mould']
CATS       = ['roof', 'door', 'window', 'kitchen', 'bathroom', 'damp_mould']
FY_LIST    = ['2023/24', '2024/25', '2025/26']

# ── Step 3: Build DATA ────────────────────────────────────────────────────────
banner('STEP 3 — Building main portal data')

rag_cols = [f'RAG_{c}' for c in COMPONENTS]
for c in rag_cols:
    if c in df_prop.columns:
        df_prop[c] = df_prop[c].fillna('Green')

df_prop['Red_Count'] = sum(
    (df_prop[c] == 'Red').astype(int) for c in rag_cols if c in df_prop.columns
)
score_dist = {}
if 'Asset Group' in df_prop.columns:
    for ag, grp in df_prop.groupby('Asset Group'):
        score_dist[ag] = {
            int(k): int(v) for k, v in
            grp['Red_Count'].value_counts().reindex(range(7), fill_value=0).items()
        }

if 'Property Count_x' in df_ag.columns:
    df_ag = df_ag.rename(columns={'Property Count_x': 'Property Count'})
if 'Property Count_y' in df_ag.columns:
    df_ag = df_ag.drop(columns=['Property Count_y'])

for fy in FY_LIST:
    fy_cat_cols = [f'{c}_{fy}' for c in CATS if f'{c}_{fy}' in df_ag.columns]
    df_ag[f'total_{fy}'] = df_ag[fy_cat_cols].sum(axis=1) if fy_cat_cols else 0

ag_meta = []
for ag, g in master.groupby('Asset Group'):
    ag_meta.append({
        'Asset Group': ag,
        'lat':       round(g['Latitude'].mean(), 5)  if g['Latitude'].notna().any()  else None,
        'lon':       round(g['Longitude'].mean(), 5) if g['Longitude'].notna().any() else None,
        'ward':      g['Ward'].dropna().mode().iloc[0]   if g['Ward'].dropna().shape[0] > 0 else '',
        'estate':    g['Estate'].dropna().mode().iloc[0] if g['Estate'].dropna().shape[0] > 0 else '',
        'block':     g['Block Name'].dropna().mode().iloc[0] if g['Block Name'].notna().any() else '',
        'total':     len(g),
        'rbg_owned': int((g['Ownership Type'] == 'COUN').sum()),
        'leasehold': int((g['Ownership Type'] == 'LEASE').sum()),
        'genfundta': int((g['Ownership Type'] == 'GENFUNDTA').sum()),
        'other_own': int((~g['Ownership Type'].isin(['COUN', 'LEASE', 'GENFUNDTA'])).sum()),
    })
df_meta = pd.DataFrame(ag_meta)

rag_ag_cols = list(dict.fromkeys(
    ['Asset Group', 'Property Count'] +
    [f'{c}_{s}' for c in COMPONENTS
     for s in ['Red_Count', 'Amber_Count', 'Green_Count', 'Pct_Red', 'RAG']
     if f'{c}_{s}' in df_ag.columns] +
    [c for c in df_ag.columns if any(f in str(c) for f in FY_LIST)] +
    [f'total_{fy}' for fy in FY_LIST if f'total_{fy}' in df_ag.columns]
))
rag_ag_cols = [c for c in rag_ag_cols if c in df_ag.columns]

df_merged = df_meta.merge(df_ag[rag_ag_cols], on='Asset Group', how='left')
df_merged = df_merged.merge(df_damp, on='Asset Group', how='left', suffixes=('', '_drop'))
df_merged = df_merged.drop(columns=[c for c in df_merged.columns if c.endswith('_drop')])
df_merged['Overall_Red_Count']   = sum(
    (df_merged.get(f'{c}_RAG', 'Green') == 'Red').astype(int)   for c in COMPONENTS)
df_merged['Overall_Amber_Count'] = sum(
    (df_merged.get(f'{c}_RAG', 'Green') == 'Amber').astype(int) for c in COMPONENTS)

EPC_RATINGS = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
if 'Asset Group' in df_prop.columns and 'EPC Rating' in df_prop.columns:
    epc_rows = [
        {'Asset Group': ag,
         'pct_epc_poor': round((g['EPC Rating'].isin(['D', 'E', 'F', 'G'])).sum() / len(g) * 100, 1)}
        for ag, g in df_prop.groupby('Asset Group') if len(g) > 0
    ]
    df_merged = df_merged.merge(pd.DataFrame(epc_rows), on='Asset Group', how='left')

# ── Build key_to_ag lookup (used by scale, cost and leak sections) ───────────
master['_key'] = master['Property Ref (UPRN)'].str.strip().str.lstrip('0')
key_to_ag = master.set_index('_key')['Asset Group'].to_dict()

# ── Add minor/major damp scale from LLM cache ────────────────────────────────
LLM_CACHE_SCALE = BASE + r'\Data\Cache\llm_categories.parquet'
if os.path.exists(LLM_CACHE_SCALE) and os.path.exists(CACHE_REPAIRS):
    try:
        df_llm_s = pd.read_parquet(LLM_CACHE_SCALE)
        df_rep_s  = pd.read_parquet(CACHE_REPAIRS)
        df_rep_s['_key'] = df_rep_s['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
        df_rep_s['desc_clean'] = df_rep_s['13_Works_Order_Description'].astype(str).str.strip()
        df_rep_s['Asset Group'] = df_rep_s['_key'].map(key_to_ag)

        # Join to get LLM scale
        df_rep_s = df_rep_s.merge(
            df_llm_s[['description','llm_category','llm_scale']],
            left_on='desc_clean', right_on='description', how='left')

        # Filter to damp/leak categories
        DAMP_CATS = {'Damp', 'Leak'}
        DAMP_WPR  = {'DPC','DPR','PSO'}
        DAMP_KW   = ['damp','mould','mold','condensation','moisture',
                     'water pen','penetrating','rising damp']

        def is_damp_scale(row):
            cat = str(row.get('llm_category',''))
            if cat in DAMP_CATS: return True
            if str(row.get('WPR_Code','')) in DAMP_WPR: return True
            return any(kw in str(row.get('13_Works_Order_Description','')).lower()
                      for kw in DAMP_KW)

        df_rep_s['is_damp'] = df_rep_s.apply(is_damp_scale, axis=1)
        df_damp_scale = df_rep_s[df_rep_s['is_damp']].copy()

        # Count minor/major per AG
        minor_ag = (df_damp_scale[df_damp_scale['llm_scale']=='Minor']
                    .groupby('Asset Group').size().reset_index(name='damp_minor_total'))
        major_ag = (df_damp_scale[df_damp_scale['llm_scale']=='Major']
                    .groupby('Asset Group').size().reset_index(name='damp_major_total'))

        # Merge into df_merged
        df_merged = df_merged.merge(minor_ag, on='Asset Group', how='left')
        df_merged = df_merged.merge(major_ag, on='Asset Group', how='left')
        df_merged['damp_minor_total'] = df_merged['damp_minor_total'].fillna(0).astype(int)
        df_merged['damp_major_total'] = df_merged['damp_major_total'].fillna(0).astype(int)

        # Calculate per-property averages
        df_merged['avg_minor_per_prop'] = (
            df_merged['damp_minor_total'] / df_merged['Property Count'].replace(0,1)
        ).round(2)
        df_merged['avg_major_per_prop'] = (
            df_merged['damp_major_total'] / df_merged['Property Count'].replace(0,1)
        ).round(2)

        n_with = (df_merged['damp_major_total'] > 0).sum()
        print(f'  Minor/major damp scale added: {n_with} AGs with major damp repairs')
    except Exception as e:
        print(f'  WARNING: Could not add scale data: {e}')
        df_merged['avg_minor_per_prop'] = 0.0
        df_merged['avg_major_per_prop'] = 0.0
else:
    df_merged['avg_minor_per_prop'] = 0.0
    df_merged['avg_major_per_prop'] = 0.0

# ── Add cost data from repairs cache ─────────────────────────────────────────
if os.path.exists(CACHE_REPAIRS):
    try:
        df_cost = pd.read_parquet(CACHE_REPAIRS)
        df_cost['_key'] = df_cost['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
        df_cost['Asset Group'] = df_cost['_key'].map(key_to_ag)
        df_cost['_cost'] = pd.to_numeric(df_cost.get('_cost', 0), errors='coerce').fillna(0)
        LLM_CACHE_COST = BASE + r'\Data\Cache\llm_categories.parquet'
        if os.path.exists(LLM_CACHE_COST):
            df_llm_cost = pd.read_parquet(LLM_CACHE_COST)[['description','llm_category','rag_category']]
            df_cost['desc_clean'] = df_cost['13_Works_Order_Description'].astype(str).str.strip()
            df_cost = df_cost.merge(df_llm_cost, left_on='desc_clean',
                                    right_on='description', how='left')
            WPR_CAT = {'DPC':'damp_mould','DPR':'damp_mould','PSO':'damp_mould',
                       'GSW':'communal_heating','GRW':'communal_heating'}
            mask = df_cost['rag_category'].isna()
            df_cost.loc[mask, 'rag_category'] = df_cost.loc[mask, 'WPR_Code'].map(WPR_CAT)
            df_cost['rag_category'] = df_cost['rag_category'].fillna('other')
        else:
            df_cost['rag_category'] = 'other'

        # Total repair cost per AG
        total_cost_ag = df_cost.groupby('Asset Group')['_cost'].sum().reset_index(name='total_repair_cost')
        prop_count = master.groupby('Asset Group').size().reset_index(name='_prop_count')

        # Cost by LLM category if available
        if 'llm_category' in df_cost.columns:
            DAMP_CATS = {'Damp','Leak'}
            df_cost['is_damp_cost'] = df_cost['llm_category'].isin(DAMP_CATS)
            damp_cost_ag = (df_cost[df_cost['is_damp_cost']]
                           .groupby('Asset Group')['_cost'].sum()
                           .reset_index(name='damp_repair_cost'))
        else:
            # Fallback to keyword matching for damp cost
            DAMP_WPR = {'DPC','DPR','PSO'}
            DAMP_KW  = ['damp','mould','mold','condensation','moisture',
                        'water pen','penetrating','rising damp']
            def is_damp_cost(row):
                if str(row.get('WPR_Code','')) in DAMP_WPR: return True
                return any(kw in str(row.get('13_Works_Order_Description','')).lower()
                          for kw in DAMP_KW)
            df_cost['is_damp_cost'] = df_cost.apply(is_damp_cost, axis=1)
            damp_cost_ag = (df_cost[df_cost['is_damp_cost']]
                           .groupby('Asset Group')['_cost'].sum()
                           .reset_index(name='damp_repair_cost'))

        # Merge into df_merged
        df_merged = df_merged.merge(total_cost_ag, on='Asset Group', how='left')
        df_merged = df_merged.merge(damp_cost_ag,  on='Asset Group', how='left')
        df_merged = df_merged.merge(prop_count,    on='Asset Group', how='left')
        df_merged['total_repair_cost'] = df_merged['total_repair_cost'].fillna(0).round(2)
        df_merged['damp_repair_cost']  = df_merged['damp_repair_cost'].fillna(0).round(2)
        df_merged['_prop_count']       = df_merged['_prop_count'].fillna(1)

        # Average cost per property
        df_merged['avg_repair_cost_per_prop'] = (
            df_merged['total_repair_cost'] / df_merged['_prop_count']
        ).round(2)
        df_merged['avg_damp_cost_per_prop'] = (
            df_merged['damp_repair_cost'] / df_merged['_prop_count']
        ).round(2)

        # Per-category cost breakdown for Overview page
        COST_CATS = ['roof','window','kitchen','bathroom',
                     'electrical','communal_heating','damp_mould','other']
        if 'rag_category' in df_cost.columns:
            for cat in COST_CATS:
                cat_cost = (df_cost[df_cost['rag_category']==cat]
                           .groupby('Asset Group')['_cost'].sum()
                           .reset_index(name=f'cost_{cat}'))
                df_merged = df_merged.merge(cat_cost, on='Asset Group', how='left')
                df_merged[f'cost_{cat}'] = df_merged[f'cost_{cat}'].fillna(0).round(2)
        else:
            for cat in COST_CATS:
                df_merged[f'cost_{cat}'] = 0.0

        n_with_cost = (df_merged['total_repair_cost'] > 0).sum()
        total_spend  = df_merged['total_repair_cost'].sum()
        damp_spend   = df_merged['damp_repair_cost'].sum()
        print(f'  Repair cost data: {n_with_cost} AGs with cost records')
        print(f'  Total repair spend: £{total_spend:,.0f}')
        print(f'  Damp/leak repair spend: £{damp_spend:,.0f} ({damp_spend/total_spend*100:.1f}% of total)')
        df_merged = df_merged.drop(columns=['_prop_count'])
    except Exception as e:
        print(f'  WARNING: Could not add cost data: {e}')
        df_merged['total_repair_cost']     = 0.0
        df_merged['damp_repair_cost']      = 0.0
        df_merged['avg_repair_cost_per_prop'] = 0.0
        df_merged['avg_damp_cost_per_prop']   = 0.0
else:
    df_merged['total_repair_cost']     = 0.0
    df_merged['damp_repair_cost']      = 0.0
    df_merged['avg_repair_cost_per_prop'] = 0.0
    df_merged['avg_damp_cost_per_prop']   = 0.0

portal_out = json.loads(df_merged.where(pd.notnull(df_merged), None).to_json(orient='records'))
portal_out = [r for r in portal_out
              if r.get('Asset Group') and str(r['Asset Group']) not in ('0', 'nan', '')]
for r in portal_out:
    r['score_dist'] = score_dist.get(r['Asset Group'], {})

# ── Add leak data from LLM cache ──────────────────────────────────────────────
LLM_CACHE_PATH = BASE + r'\Data\Cache\llm_categories.parquet'
if os.path.exists(LLM_CACHE_PATH):
    try:
        df_llm_leaks = pd.read_parquet(LLM_CACHE_PATH)
        df_llm_leaks = df_llm_leaks[df_llm_leaks['llm_category'] == 'Leak'].copy()

        # Join back to repairs to get property keys
        df_rep_cache = pd.read_parquet(CACHE_REPAIRS)
        df_rep_cache['_key'] = df_rep_cache['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
        df_rep_cache['desc_clean'] = df_rep_cache['13_Works_Order_Description'].astype(str).str.strip()
        df_leaks = df_rep_cache.merge(
            df_llm_leaks[['description','llm_leak_cause','llm_leak_impact']],
            left_on='desc_clean', right_on='description', how='inner')
        df_leaks['Asset Group'] = df_leaks['_key'].map(key_to_ag)
        df_leaks = df_leaks.dropna(subset=['Asset Group'])

        # AG-level leak summary
        leak_ag = {}
        for ag, grp in df_leaks.groupby('Asset Group'):
            total_props_in_ag = master[master['Asset Group']==ag].shape[0]
            props_with_leaks = grp['_key'].nunique()
            leak_ag[ag] = {
                'total_leaks':      int(len(grp)),
                'props_with_leaks': int(props_with_leaks),
                'pct_with_leaks':   round(props_with_leaks/total_props_in_ag*100,1) if total_props_in_ag>0 else 0,
                'cause_roof':       int((grp['llm_leak_cause']=='Roof').sum()),
                'cause_plumbing':   int((grp['llm_leak_cause']=='Plumbing').sum()),
                'cause_unknown':    int((grp['llm_leak_cause']=='Unknown').sum()),
                'impact_structural':int((grp['llm_leak_impact']=='Structural/Wall').sum()),
                'impact_damp':      int((grp['llm_leak_impact']=='Damp').sum()),
                'impact_electrical':int((grp['llm_leak_impact']=='Electrical').sum()),
            }

        # Also compute properties with BOTH leaks AND damp
        DAMP_WPR = {'DPC','DPR','PSO'}
        DAMP_KW  = ['damp','mould','mold','condensation','moisture',
                    'water pen','penetrating','rising damp']
        def is_damp_rep(row):
            if str(row['WPR_Code']) in DAMP_WPR: return True
            return any(kw in str(row['13_Works_Order_Description']).lower() for kw in DAMP_KW)
        df_rep_cache['is_damp'] = df_rep_cache.apply(is_damp_rep, axis=1)
        props_with_damp = set(df_rep_cache[df_rep_cache['is_damp']]['_key'].unique())
        props_with_leaks_set = set(df_leaks['_key'].unique())
        both = props_with_damp & props_with_leaks_set

        for ag, grp in df_leaks.groupby('Asset Group'):
            ag_props = set(master[master['Asset Group']==ag]['_key'].unique()) if '_key' in master.columns else set()
            if not ag_props:
                ag_props = set(master[master['Asset Group']==ag]['Property Ref (UPRN)'].str.strip().str.lstrip('0').unique())
            both_in_ag = len(both & ag_props)
            if ag in leak_ag:
                leak_ag[ag]['both_leak_damp'] = both_in_ag

        # Merge into portal_out
        for r in portal_out:
            ag = r.get('Asset Group')
            ld = leak_ag.get(ag, {})
            r['total_leaks']       = ld.get('total_leaks', 0)
            r['props_with_leaks']  = ld.get('props_with_leaks', 0)
            r['pct_with_leaks']    = ld.get('pct_with_leaks', 0.0)
            r['cause_roof']        = ld.get('cause_roof', 0)
            r['cause_plumbing']    = ld.get('cause_plumbing', 0)
            r['cause_unknown']     = ld.get('cause_unknown', 0)
            r['impact_structural'] = ld.get('impact_structural', 0)
            r['impact_damp']       = ld.get('impact_damp', 0)
            r['impact_electrical'] = ld.get('impact_electrical', 0)
            r['both_leak_damp']    = ld.get('both_leak_damp', 0)

        print(f'  Leak data added: {len(leak_ag)} AGs with leak records')
        total_leaks = sum(v['total_leaks'] for v in leak_ag.values())
        print(f'  Total leak work orders: {total_leaks:,}')
        print(f'  Properties with both leaks and damp: {len(both):,}')
    except Exception as e:
        print(f'  WARNING: Could not add leak data: {e}')
        for r in portal_out:
            for k in ['total_leaks','props_with_leaks','pct_with_leaks','cause_roof',
                      'cause_plumbing','cause_unknown','impact_structural',
                      'impact_damp','impact_electrical','both_leak_damp']:
                r[k] = 0
else:
    print('  No LLM cache found — leak data not available')
    for r in portal_out:
        for k in ['total_leaks','props_with_leaks','pct_with_leaks','cause_roof',
                  'cause_plumbing','cause_unknown','impact_structural',
                  'impact_damp','impact_electrical','both_leak_damp']:
            r[k] = 0

print(f'  Portal data: {len(portal_out)} asset groups')


# ── Step 3b: Generate AG narrative summaries (GPT-5.6 Luna) ──────────────────
banner('STEP 3b — Generating asset group narrative summaries')

AG_SUMMARY_CACHE = BASE + r'\Data\Cache\ag_summaries.json'
OPENAI_API_KEY   = os.environ.get('OPENAI_API_KEY', '')

# Load existing summaries if available
ag_summaries = {}
if os.path.exists(AG_SUMMARY_CACHE):
    with open(AG_SUMMARY_CACHE, 'r', encoding='utf-8') as f:
        ag_summaries = json.load(f)
    print(f'  Loaded {len(ag_summaries)} existing summaries from cache')

# Identify AGs that need a new or updated summary
# Regenerate if: no summary exists, or key data has changed significantly
ags_needing_summary = []
for r in portal_out:
    ag = r.get('Asset Group')
    if not ag: continue
    existing = ag_summaries.get(ag, {})
    # Check if summary exists and data hasn't changed materially
    if (not existing.get('summary') or
        existing.get('damp_rag') != r.get('Damp RAG') or
        existing.get('total_leaks') != r.get('total_leaks', 0)):
        ags_needing_summary.append(r)

print(f'  AGs needing summary: {len(ags_needing_summary)} of {len(portal_out)}')

if ags_needing_summary and OPENAI_API_KEY:
    try:
        import openai, asyncio, random as _random

        async def generate_summary(client, sem, r, prop_rag_df):
            async with sem:
                ag = r.get('Asset Group', '')
                total = r.get('Property Count') or r.get('total', 0)
                damp_rag    = r.get('Damp RAG', 'Green')
                pct_1plus   = r.get('% w/ 1+ Damp Repairs', 0) or 0
                pct_2plus   = r.get('% w/ 2+ Damp Repairs', 0) or 0
                total_damp  = r.get('Total Damp Work Orders', 0) or 0
                avg_repairs = r.get('Avg Damp Repairs per Property', 0) or 0
                sev_severe  = r.get('% ATT Severe', 0) or 0
                sev_mod     = r.get('% ATT Moderate', 0) or 0
                total_leaks = r.get('total_leaks', 0)
                pct_leaks   = r.get('pct_with_leaks', 0)
                both_ld     = r.get('both_leak_damp', 0)
                cause_roof  = r.get('cause_roof', 0)
                cause_plumb = r.get('cause_plumbing', 0)
                imp_str     = r.get('impact_structural', 0)
                imp_damp    = r.get('impact_damp', 0)
                imp_elec    = r.get('impact_electrical', 0)
                ward        = r.get('ward', '')

                # Get worst property for this AG
                worst_prop = ''
                if prop_rag_df is not None and 'Asset Group' in prop_rag_df.columns:
                    ag_props = prop_rag_df[prop_rag_df['Asset Group'] == ag]
                    if len(ag_props) > 0 and 'Damp_Repair_Count' in ag_props.columns:
                        worst = ag_props.nlargest(1, 'Damp_Repair_Count')
                        if len(worst) > 0:
                            addr = worst.iloc[0].get('Address', '')
                            cnt  = worst.iloc[0].get('Damp_Repair_Count', 0)
                            if addr and int(float(cnt or 0)) > 0:
                                worst_prop = f'{addr} ({int(float(cnt))} damp work orders)'

                prompt = f"""Write a concise 3-4 sentence asset group summary for a housing asset manager.
Asset group: {ag}
Ward: {ward}
Total properties: {total}
Damp RAG rating: {damp_rag}
% with 1+ damp repairs: {pct_1plus}%
% with 2+ damp repairs (recurrent): {pct_2plus}%
Total damp work orders: {total_damp}
Avg damp repairs per property: {avg_repairs}
Surveyor severe: {sev_severe}%  Surveyor moderate: {sev_mod}%
Total leak work orders: {total_leaks}
% properties with leaks: {pct_leaks}%
Properties with both leaks and damp: {both_ld}
Leak cause - Roof: {cause_roof}  Plumbing: {cause_plumb}
Leak impact - Structural: {imp_str}  Damp: {imp_damp}  Electrical: {imp_elec}
Worst property: {worst_prop if worst_prop else 'N/A'}

Write a professional, factual summary covering: main damp/leak issues, severity, any notable patterns (roof leaks, recurring damp, surveyor concerns), and the worst outlier if applicable. Do not use bullet points. Do not start with the asset group name. Keep it under 80 words."""

                for attempt in range(3):
                    try:
                        resp = await client.chat.completions.create(
                            model='gpt-5.6-luna',
                            messages=[
                                {'role': 'system', 'content': 'You are a housing asset management analyst writing factual property condition summaries. Be concise and factual. Write exactly 3-4 sentences maximum.'},
                                {'role': 'user',   'content': prompt},
                            ],
                            max_completion_tokens=300,
                            stream=False,
                        )
                        # Extract text from response
                        summary_text = ''
                        if hasattr(resp, 'choices') and resp.choices:
                            msg = resp.choices[0].message
                            if hasattr(msg, 'content') and msg.content:
                                summary_text = msg.content
                            elif hasattr(msg, 'text') and msg.text:
                                summary_text = msg.text
                        if not summary_text and hasattr(resp, 'output_text'):
                            summary_text = resp.output_text or ''
                        summary_text = (summary_text or '').strip()
                        if summary_text:
                            return ag, {
                                'summary':     summary_text,
                                'damp_rag':    damp_rag,
                                'total_leaks': total_leaks,
                            }
                        else:
                            raise ValueError('Empty response from API')
                    except Exception as e:
                        if attempt == 2:
                            print(f'    Failed {ag[:30]}: {e}')
                            return ag, {'summary': '', 'damp_rag': damp_rag, 'total_leaks': total_leaks}
                        await asyncio.sleep(2 ** attempt + _random.uniform(0,1))

        async def run_summaries(ags, prop_rag_df):
            client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
            sem    = asyncio.Semaphore(15)
            tasks  = [generate_summary(client, sem, r, prop_rag_df) for r in ags]
            results = []
            done = 0
            for coro in asyncio.as_completed(tasks):
                res = await coro
                results.append(res)
                done += 1
                if done % 20 == 0 or done == len(tasks):
                    print(f'  Summaries: {done}/{len(tasks)} complete', flush=True)
            return results

        # Load prop RAG for worst property lookup
        try:
            prop_rag_for_summary = pd.read_excel(RAG_FILE, sheet_name='Property RAG', header=1)
            prop_rag_for_summary['Damp_Repair_Count'] = pd.to_numeric(
                prop_rag_for_summary.get('Damp_Repair_Count', 0), errors='coerce').fillna(0)
        except:
            prop_rag_for_summary = None

        import asyncio as _asyncio
        new_results = _asyncio.run(run_summaries(ags_needing_summary, prop_rag_for_summary))

        for item in new_results:
            if item and len(item) == 2:
                ag, data = item
                if ag and isinstance(data, dict):
                    if data.get('summary'):
                        ag_summaries[ag] = data
                    else:
                        print(f'  WARNING: Empty summary for {ag[:40]}')

        # Save cache
        print(f'  new_results count: {len(new_results)}')
        print(f'  Sample result: {new_results[0] if new_results else "EMPTY"}')
        os.makedirs(os.path.dirname(AG_SUMMARY_CACHE), exist_ok=True)
        with open(AG_SUMMARY_CACHE, 'w', encoding='utf-8') as f:
            json.dump(ag_summaries, f, ensure_ascii=False, indent=2)
        print(f'  Saved {len(ag_summaries)} summaries to cache')

    except ImportError:
        print('  openai not installed — skipping summaries')
    except Exception as e:
        print(f'  WARNING: Summary generation failed: {e}')
elif not OPENAI_API_KEY:
    print('  No OPENAI_API_KEY set — skipping summary generation')
    print('  Set $env:OPENAI_API_KEY before running to enable summaries')

# Merge summaries into portal_out
for r in portal_out:
    ag = r.get('Asset Group', '')
    r['ag_summary'] = ag_summaries.get(ag, {}).get('summary', '')

n_with_summary = sum(1 for r in portal_out if r.get('ag_summary'))
print(f'  {n_with_summary} asset groups have narrative summaries')

# ── Step 4: FY totals ─────────────────────────────────────────────────────────
banner('STEP 4 — FY repair totals')

fy_totals = {
    'labels': FY_LIST,
    'categories': {
        cat: [int(df_ag[f'{cat}_{fy}'].sum()) if f'{cat}_{fy}' in df_ag.columns else 0
              for fy in FY_LIST]
        for cat in CATS
    },
    'total': [
        int(df_ag[f'total_{fy}'].sum()) if f'total_{fy}' in df_ag.columns else 0
        for fy in FY_LIST
    ]
}
print(f'  FY totals: {fy_totals["total"]}')

# ── Step 5: Retrofit component data ──────────────────────────────────────────
banner('STEP 5 — Retrofit components')

RETROFIT_COMPS = [
    'Window Type', 'Private Front Entrance Door', 'Private Back Entrance Door',
    'Loft Insulation', 'Cavity Wall Insulation', 'Solid Wall Insulation',
    'Primary Heating System', 'Heat Distribution', 'Flat Roof Covering',
    'Pitched Roof Covering', 'Bathroom Fan', 'Kitchen Fan',
]
retrofit_out = []

if os.path.exists(CACHE_REP):
    df_rep = pd.read_parquet(CACHE_REP)
    df_rep['_key'] = df_rep['UPRN'].str.strip().str.lstrip('0')
    df_rep['Year_Due_Int'] = pd.to_numeric(df_rep['Year Due'], errors='coerce')
    key_to_ag = master.set_index('_key')['Asset Group'].to_dict()
    df_rep['Asset_Group'] = df_rep['_key'].map(key_to_ag)

    for (ag, comp), grp in df_rep[df_rep['Component'].isin(RETROFIT_COMPS)].groupby(
            ['Asset_Group', 'Component']):
        min_yr = grp['Year_Due_Int'].min()
        retrofit_out.append({
            'Asset Group':    ag,
            'Component':      comp,
            'Min_Year_Due':   None if pd.isna(min_yr) else int(min_yr),
            'Due_Within_5yr': int((grp['Year_Due_Int'] <= 2030).sum()),
            'Total_Records':  len(grp),
        })
    print(f'  Retrofit records: {len(retrofit_out)}')
else:
    print('  WARNING: REP cache not found — retrofit data will be empty')

# ── Step 6: Stock condition survey data ───────────────────────────────────────
banner('STEP 6 — Stock condition data')

ag_total_props = master.groupby('Asset Group')['Property Ref (UPRN)'].count().to_dict()

sc_rows = []
if os.path.exists(CACHE_REP):
    df_rep_s = pd.read_parquet(CACHE_REP)
    df_rep_s['_key'] = df_rep_s['UPRN'].str.strip().str.lstrip('0')
    df_rep_s['Asset_Group'] = df_rep_s['_key'].map(key_to_ag)
    df_rep_s['Survey_Year'] = pd.to_datetime(df_rep_s['Survey Date'], errors='coerce').dt.year
    df_rep_s['Year_Due_Int'] = pd.to_numeric(df_rep_s['Year Due'], errors='coerce')

    def get_consultant(surveyor):
        s = str(surveyor).lower() if pd.notna(surveyor) else ''
        if 'potter raper' in s: return 'Potter Raper'
        if 'martin arnold' in s: return 'Martin Arnold'
        if 'savills' in s: return 'Savills'
        if 'fft' in s: return 'FFT'
        return 'Internal/Other'

    df_rep_s['Consultant'] = df_rep_s['Surveyor'].apply(get_consultant)

    KEY_COMPS = {
        'Bathroom Primary': 'bathroom_due', 'Kitchen': 'kitchen_due',
        'Pitched Roof Covering': 'roof_due', 'Flat Roof Covering': 'roof_due',
        'Primary Heating System': 'heating_due', 'Wiring': 'electrical_due',
        'Window Type': 'windows_due', 'Private Front Entrance Door': 'doors_due',
    }
    df_rep_s['comp_cat'] = df_rep_s['Component'].map(KEY_COMPS)
    comp_min = (df_rep_s[df_rep_s['comp_cat'].notna()]
                .groupby(['Asset_Group', 'comp_cat'])['Year_Due_Int'].min()
                .reset_index())
    comp_pivot = comp_min.pivot(index='Asset_Group', columns='comp_cat',
                                values='Year_Due_Int').reset_index()
    comp_pivot.columns.name = None

    uprn_latest = (df_rep_s.sort_values('Survey_Year', ascending=False)
                   .groupby('_key').first()[['Survey_Year', 'Consultant']]
                   .reset_index())
    uprn_latest['Asset_Group'] = uprn_latest['_key'].map(key_to_ag)

    def survey_status(yr):
        if pd.isna(yr): return 'Not surveyed'
        yr = int(yr)
        if yr <= 2018: return 'Overdue'
        if yr <= 2021: return 'Partial'
        return 'Current'
    uprn_latest['Status'] = uprn_latest['Survey_Year'].apply(survey_status)

    for ag, grp in uprn_latest.groupby('Asset_Group'):
        total = int(ag_total_props.get(ag, 0))
        surv  = len(grp)
        cons  = grp['Consultant'].dropna().mode().iloc[0] if grp['Consultant'].dropna().shape[0] > 0 else 'Unknown'
        latest = grp['Survey_Year'].max()
        status = (grp['Status'].value_counts().index[0]
                  if len(grp) > 0 else 'Not surveyed')
        cp = comp_pivot[comp_pivot['Asset_Group'] == ag]

        def yr(col):
            if cp.empty or col not in cp.columns: return None
            v = cp[col].iloc[0]
            return None if pd.isna(v) else int(v)

        sc_rows.append({
            'ag': ag, 'total': total, 'surveyed': surv,
            'not_surveyed': max(0, total - surv),
            'last_survey': None if pd.isna(latest) else int(latest),
            'consultant': cons, 'status': status,
            'pct_surveyed': round(surv / total * 100, 1) if total > 0 else 0,
            'cons_detail': {},
            'bathroom_due': yr('bathroom_due'), 'kitchen_due': yr('kitchen_due'),
            'roof_due': yr('roof_due'), 'heating_due': yr('heating_due'),
            'electrical_due': yr('electrical_due'), 'windows_due': yr('windows_due'),
            'doors_due': yr('doors_due'),
        })

    flagged_5yr = {
        elem: sum(1 for r in sc_rows if r.get(elem) and r[elem] <= 2030)
        for elem in ['bathroom_due', 'kitchen_due', 'roof_due', 'heating_due',
                     'electrical_due', 'windows_due', 'doors_due']
    }
    sc_data = {
        'kpis': {
            'total_props':     int(len(master)),
            'total_surveyed':  int(uprn_latest['_key'].nunique()),
            'ag_current':      sum(1 for r in sc_rows if r['status'] == 'Current'),
            'ag_overdue':      sum(1 for r in sc_rows if r['status'] == 'Overdue'),
            'ag_partial':      sum(1 for r in sc_rows if r['status'] == 'Partial'),
            'ag_not_surveyed': sum(1 for r in sc_rows if r['status'] == 'Not surveyed'),
            'flagged_5yr':     flagged_5yr,
        },
        'rows': sc_rows,
    }
    print(f'  SC rows: {len(sc_rows)} asset groups')
else:
    sc_data = {
        'kpis': {'total_props': int(len(master)), 'total_surveyed': 0,
                 'ag_current': 0, 'ag_overdue': 0, 'ag_partial': 0,
                 'ag_not_surveyed': len(df_ag), 'flagged_5yr': {}},
        'rows': [],
    }
    print('  WARNING: REP cache not found — stock condition data will be empty')

# ── Step 7: Property damp lookup ─────────────────────────────────────────────
banner('STEP 7 — Property damp lookup')

prop_lookup = {}
if os.path.exists(CACHE_REP) and os.path.exists(CACHE_REPAIRS):
    DAMP_COMPS = {
        'Damp and Mould Growth': 'damp_due', 'Loft Insulation': 'loft_due',
        'Cavity Wall Insulation': 'cwi_due', 'Solid Wall Insulation': 'ewi_due',
        'External Wall Finish': 'ewi_due', 'Spalling Brickwork': 'repoint_due',
        'Window Type': 'window_due', 'Bathroom Fan': 'fan_due',
    }
    df_rep['comp_cat_d'] = df_rep['Component'].map(DAMP_COMPS)
    comp_min_d = (df_rep[df_rep['comp_cat_d'].notna()]
                  .groupby(['_key', 'comp_cat_d'])['Year_Due_Int'].min()
                  .reset_index())
    comp_pivot_d = comp_min_d.pivot(index='_key', columns='comp_cat_d',
                                    values='Year_Due_Int').reset_index()
    comp_pivot_d.columns.name = None

    df_repairs = pd.read_parquet(CACHE_REPAIRS)
    df_repairs['_key'] = df_repairs['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
    damp_mask = df_repairs['13_Works_Order_Description'].str.lower().str.contains(
        'damp|mould|mold', na=False)
    damp_counts = df_repairs[damp_mask].groupby('_key').size().reset_index(name='repairs')

    df_prop2 = df_prop[['Property Ref (UPRN)', 'Address', 'Postcode',
                         'Asset Group', '_key', 'RAG_Damp_Mould']].copy() if '_key' in df_prop.columns else \
               df_prop[['Property Ref (UPRN)', 'Address', 'Postcode', 'Asset Group']].copy()
    if '_key' not in df_prop2.columns:
        df_prop2['_key'] = df_prop2['Property Ref (UPRN)'].str.strip().str.lstrip('0')

    df_prop2 = (df_prop2
                .merge(comp_pivot_d, on='_key', how='left')
                .merge(damp_counts, on='_key', how='left'))
    df_prop2['repairs'] = df_prop2['repairs'].fillna(0).astype(int)
    df_prop2['damp_rag'] = df_prop2['RAG_Damp_Mould'].fillna('Green') if 'RAG_Damp_Mould' in df_prop2.columns else 'Green'

    for ag, grp in df_prop2.groupby('Asset Group'):
        rows = []
        for _, r in grp.iterrows():
            def yr(v):
                try: return int(float(v)) if pd.notna(v) else None
                except: return None
            entry = {
                'uprn': r['Property Ref (UPRN)'], 'addr': r['Address'],
                'post': r['Postcode'], 'damp_rag': r['damp_rag'],
                'repairs': int(r['repairs']),
                'damp_due': yr(r.get('damp_due')), 'loft_due': yr(r.get('loft_due')),
                'cwi_due': yr(r.get('cwi_due')), 'ewi_due': yr(r.get('ewi_due')),
                'repoint_due': yr(r.get('repoint_due')),
                'window_due': yr(r.get('window_due')), 'fan_due': yr(r.get('fan_due')),
            }
            if (entry['repairs'] > 0 or
                    any(entry.get(k) and entry[k] <= 2030
                        for k in ['damp_due', 'loft_due', 'cwi_due', 'ewi_due',
                                  'repoint_due', 'window_due'])):
                entry = {k: v for k, v in entry.items()
                         if v is not None and v != 0
                         or k in ('uprn', 'addr', 'post', 'damp_rag', 'repairs')}
                rows.append(entry)
        if rows:
            prop_lookup[ag] = rows

    total_pl = sum(len(v) for v in prop_lookup.values())
    print(f'  Property lookup: {total_pl:,} properties across {len(prop_lookup)} groups')
else:
    print('  WARNING: Cache files not found — property damp lookup will be empty')

# ── Step 8: Block compliance data ─────────────────────────────────────────────
banner('STEP 8 — Block compliance data')

COMMUNAL_COMPS = {
    'Communal Fire Alarm System': 'Fire Safety', 'Communal Emergency Lighting': 'Fire Safety',
    'Communal Mains Electrical Wiring': 'Electrical', 'Communal Wiring / Lighting': 'Electrical',
    'Communal Wiring': 'Electrical',
    'Door Entry': 'Access & Security', 'Communal Front Entrance Door': 'Access & Security',
    'Communal Side Entrance Door': 'Access & Security', 'Communal Back Entrance Door': 'Access & Security',
    'Communal Flat Roof Main': 'Roof & Structure', 'Communal Pitched Roof Main': 'Roof & Structure',
    'Communal Flat Roof Secondary': 'Roof & Structure', 'Communal Pitched Roof Secondary': 'Roof & Structure',
    'Flat Roof Covering': 'Roof & Structure', 'Spalling Brickwork': 'Roof & Structure',
    'External Wall Finish': 'Roof & Structure', 'External Wall Construction': 'Roof & Structure',
    'Communal Balcony Rail Type': 'Balconies & Rails', 'Communal Balcony': 'Balconies & Rails',
    'Communal Balustrading': 'Balconies & Rails',
    'Communal Walkway Floor Covering': 'Communal Areas', 'Communal Stairs Floor Covering': 'Communal Areas',
    'Communal External Lighting': 'Communal Areas',
    'Communal Heating System': 'Communal Heating', 'Communal Water': 'Communal Heating',
}
BLOCK_PROG_COMPS = {
    'Window Type': 'Windows', 'Private Front Entrance Door': 'Access & Security',
    'Wiring': 'Electrical', 'Heat Distribution': 'Communal Heating',
    'Primary Heating System': 'Communal Heating', 'Smoke Alarms': 'Fire Safety',
    'CO Alarms': 'Fire Safety', 'Private Balcony Rail Type': 'Balconies & Rails',
    'Private Balcony Rail Fixings': 'Balconies & Rails',
}

block_data_out = {'blocks': [], 'comp_summary': [], 'comp_detail': [], 'block_props': {}}

if os.path.exists(CACHE_REP):
    df_rep_b = pd.read_parquet(CACHE_REP)
    df_rep_b['_key'] = df_rep_b['UPRN'].str.strip().str.lstrip('0')
    df_rep_b['Block_Name_Asset'] = df_rep_b['_key'].map(
        master.set_index('_key')['Block Name (Asset)'].to_dict())
    df_rep_b['Block_Size'] = df_rep_b['_key'].map(
        master.set_index('_key')['Block Size'].to_dict())
    df_rep_b['Year_Due_Int'] = pd.to_numeric(df_rep_b['Year Due'], errors='coerce')
    df_rep_b['Survey_Year'] = pd.to_datetime(df_rep_b['Survey Date'], errors='coerce').dt.year

    def extract_bsr(note):
        if pd.isna(note): return None
        m = re.search(r'HRB\w+', str(note))
        return m.group(0).strip() if m else None
    master['BSR_Number'] = master['Notes'].apply(extract_bsr)
    df_rep_b['BSR_Number'] = df_rep_b['_key'].map(
        master.set_index('_key')['BSR_Number'].to_dict())

    df_rep_b['Block_Category'] = df_rep_b['Component'].map(COMMUNAL_COMPS)

    valid_blocks = master[
        master['Block Name (Asset)'].notna() &
        ~master['Block Name (Asset)'].isin(
            ['not a block', 'not a block (F/M)', 'nan', '0', ''])
    ].copy()
    block_total = valid_blocks.groupby('Block Name (Asset)').size().to_dict()

    # Block programme detection
    prog_rows = []
    for comp, cat in BLOCK_PROG_COMPS.items():
        cd = df_rep_b[df_rep_b['Component'] == comp].copy()
        for block, grp in cd.groupby('Block_Name_Asset'):
            total = block_total.get(block, 0)
            if total == 0: continue
            years = grp['Year_Due_Int'].dropna()
            if len(years) == 0: continue
            if years.nunique() == 1 and len(grp) / total >= 0.80:
                surv = grp['Surveyor'].dropna()
                note = grp['Notes'].dropna().astype(str)
                note = note[note.str.len() > 15]
                prog_rows.append({
                    'Block_Name_Asset': block, 'Component': comp,
                    'Block_Category': cat, 'min_yr': int(years.iloc[0]),
                    'last_survey': grp['Survey_Year'].max(),
                    'surveyor': surv.mode().iloc[0] if len(surv) > 0 else None,
                    'category': cat, 'records': len(grp),
                    'sample_note': note.iloc[0] if len(note) > 0 else None,
                    'is_programme': True, 'coverage_pct': round(len(grp) / total * 100, 1),
                })

    # Build block metadata
    block_meta = []
    for block, grp in valid_blocks.groupby('Block Name (Asset)'):
        bsr = grp['BSR_Number'].dropna().unique()
        sizes = grp['Block Size'].dropna()
        wards = grp['Ward'].dropna()
        ags   = grp['Asset Group'].dropna()
        block_meta.append({
            'block':        block,
            'block_size':   sizes.mode().iloc[0] if len(sizes) > 0 else '',
            'ward':         wards.mode().iloc[0] if len(wards) > 0 else '',
            'asset_group':  ags.mode().iloc[0] if len(ags) > 0 else '',
            'total_props':  len(grp),
            'bsr_number':   bsr[0] if len(bsr) > 0 else None,
            'is_high_rise': bool(grp['Block Size'].isin(['High', 'HIgh']).any()),
            'is_registered':bool(len(bsr) > 0),
            'lat': round(pd.to_numeric(grp['Latitude'], errors='coerce').mean(), 5),
            'lon': round(pd.to_numeric(grp['Longitude'], errors='coerce').mean(), 5),
        })

    # Component detail
    bc = df_rep_b[df_rep_b['Block_Category'].notna() & df_rep_b['Block_Name_Asset'].notna()]

    def safe_mode(x): x = x.dropna(); return x.mode().iloc[0] if len(x) > 0 else None
    def best_note(x):
        x = x.dropna().astype(str)
        x = x[x.str.len() > 15]
        return x.iloc[0] if len(x) > 0 else None

    comm_det = bc.groupby(['Block_Name_Asset', 'Component']).agg(
        min_yr=('Year_Due_Int', 'min'), last_survey=('Survey_Year', 'max'),
        surveyor=('Surveyor', safe_mode), category=('Block_Category', 'first'),
        records=('UPRN', 'count'), sample_note=('Notes', best_note),
        is_programme=('Block_Category', lambda x: False),
    ).reset_index()
    comm_det['coverage_pct'] = None

    # Merge programme records
    if prog_rows:
        df_prog = pd.DataFrame(prog_rows)
        existing = set(zip(comm_det['Block_Name_Asset'], comm_det['Component']))
        df_prog = df_prog[~df_prog.apply(
            lambda r: (r['Block_Name_Asset'], r['Component']) in existing, axis=1)]
        comp_det_final = pd.concat([comm_det, df_prog], ignore_index=True)
    else:
        comp_det_final = comm_det

    # Comp summary
    comp_sum = comp_det_final.groupby(['Block_Name_Asset', 'category']).agg(
        min_yr=('min_yr', 'min'), last_survey=('last_survey', 'max'),
        records=('records', 'sum')
    ).reset_index().rename(columns={'category': 'Block_Category'})

    # Block props - all blocks
    block_props = {}
    for block, grp in valid_blocks.groupby('Block Name (Asset)'):
        block_props[block] = [
            {'uprn': r['Property Ref (UPRN)'], 'addr': r['Address'],
             'post': r['Postcode'], 'own': r['Ownership Type']}
            for _, r in grp.iterrows()
        ]

    def clean(v):
        try:
            if pd.isna(v): return None
        except: pass
        if isinstance(v, float):
            try:
                if v == int(v): return int(v)
            except: pass
        return v

    df_blocks_df = pd.DataFrame(block_meta)
    block_data_out = {
        'blocks':       [{k: clean(v) for k, v in r.items()} for r in df_blocks_df.to_dict('records')],
        'comp_summary': [{k: clean(v) for k, v in r.items()} for r in comp_sum.to_dict('records')],
        'comp_detail':  [{k: clean(v) for k, v in r.items()} for r in comp_det_final.to_dict('records')],
        'block_props':  block_props,
    }
    print(f'  Blocks: {len(block_meta)} | Comp detail: {len(comp_det_final)} | Block props: {len(block_props)}')
else:
    print('  WARNING: REP cache not found — block data will be empty')

# ── Step 9: Retrofit summary data ─────────────────────────────────────────────
banner('STEP 9 — Retrofit & EPC data')

ag_epc = {}
ag_retrofit_summary = {}
for ag, g in master.groupby('Asset Group'):
    total = len(g)
    epc_dist = {r: int((g['EPC Rating'] == r).sum()) for r in EPC_RATINGS}
    poor = sum(epc_dist.get(r, 0) for r in ['D', 'E', 'F', 'G'])
    ag_epc[ag] = {
        'total': total, 'epc_dist': epc_dist,
        'pct_poor': round(poor / total * 100, 1) if total > 0 else 0,
        'avg_sap': round(pd.to_numeric(g['SAP Score'], errors='coerce').mean(), 1),
    }

if os.path.exists(CACHE_REP):
    RETROFIT_PROP = {
        'Window Type': 'wins', 'Private Front Entrance Door': 'door',
        'Loft Insulation': 'loft', 'Cavity Wall Insulation': 'cwi',
        'Solid Wall Insulation': 'ewi',
    }
    df_rep['comp_rt'] = df_rep['Component'].map(RETROFIT_PROP)
    comp_rt = (df_rep[df_rep['comp_rt'].notna()]
               .groupby(['_key', 'comp_rt'])['Year_Due_Int'].min()
               .reset_index())
    comp_rt_pivot = comp_rt.pivot(index='_key', columns='comp_rt',
                                  values='Year_Due_Int').reset_index()
    comp_rt_pivot.columns.name = None

    df_rt = master[['Property Ref (UPRN)', 'Asset Group', '_key']].copy()
    df_rt = df_rt.merge(comp_rt_pivot, on='_key', how='left')

    print(f'  comp_rt_pivot columns: {list(comp_rt_pivot.columns)}')
    if "wins" in comp_rt_pivot.columns:
        n_wins = comp_rt_pivot["wins"].notna().sum()
        wins_le2030 = (comp_rt_pivot["wins"].notna() & (comp_rt_pivot["wins"]<=2030)).sum()
        print(f'  comp_rt_pivot wins: {n_wins} records, {wins_le2030} due <=2030')
    else:
        print(f'  WARNING: no wins column in comp_rt_pivot')
        print(f'  comp_rt categories: {df_rep["comp_rt"].value_counts().to_dict()}')
    for ag, g in df_rt.groupby('Asset Group'):
        total = len(g)
        def pct(col):
            if col not in g.columns: return 0
            return round((g[col].notna() & (g[col] <= 2030)).sum() / total * 100, 1) if total > 0 else 0
        ag_retrofit_summary[ag] = {
            'total':    total,
            'pct_win':  pct('wins'),
            'pct_door': pct('door'),
            'pct_loft': pct('loft'),
            'pct_cwi':  pct('cwi'),
            'pct_ewi':  pct('ewi'),
        }

# Build property lookup for retrofit drill-down
rt_prop_lookup = {}
if os.path.exists(CACHE_REP):
    # Add EPC, damp and component data per property
    df_rt_full = master[['Property Ref (UPRN)', 'Address', 'Postcode',
                          'Asset Group', 'EPC Rating', 'SAP Score', '_key']].copy()
    df_rt_full = df_rt_full.merge(comp_rt_pivot, on='_key', how='left')
    if os.path.exists(CACHE_REPAIRS):
        DAMP_WPR_RT = {'DPC', 'DPR', 'PSO'}
        DAMP_KW_RT  = ['damp', 'mould', 'mold', 'condensation', 'moisture',
                        'water pen', 'penetrating', 'rising damp']
        df_r3 = pd.read_parquet(CACHE_REPAIRS)
        df_r3['_key'] = df_r3['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
        def is_damp_rt(row):
            if str(row['WPR_Code']) in DAMP_WPR_RT: return True
            return any(kw in str(row['13_Works_Order_Description']).lower() for kw in DAMP_KW_RT)
        df_r3['is_damp'] = df_r3.apply(is_damp_rt, axis=1)
        dc_rt = df_r3[df_r3['is_damp']].groupby('_key').size().reset_index(name='damp')
        df_rt_full = df_rt_full.merge(dc_rt, on='_key', how='left')
        df_rt_full['damp'] = df_rt_full['damp'].fillna(0).astype(int)
    else:
        df_rt_full['damp'] = 0

    if 'RAG_Damp_Mould' in df_prop.columns:
        df_prop_rag_rt = df_prop[['Property Ref (UPRN)', 'RAG_Damp_Mould']].copy()
        df_prop_rag_rt['_key'] = df_prop_rag_rt['Property Ref (UPRN)'].str.strip().str.lstrip('0')
        df_rt_full = df_rt_full.merge(
            df_prop_rag_rt[['_key', 'RAG_Damp_Mould']].rename(columns={'RAG_Damp_Mould': 'damp_rag'}),
            on='_key', how='left')
        df_rt_full['damp_rag'] = df_rt_full['damp_rag'].fillna('Green')
    else:
        df_rt_full['damp_rag'] = 'Green'

    EPC_VALID = set('ABCDEFG')
    for ag, g in df_rt_full.groupby('Asset Group'):
        rows = []
        for _, r in g.iterrows():
            def yr_rt(v):
                try: return int(float(v)) if pd.notna(v) else None
                except: return None
            entry = {
                'uprn': r['Property Ref (UPRN)'], 'addr': r['Address'],
                'post': r['Postcode'],
                'epc':  r['EPC Rating'] if r['EPC Rating'] in EPC_VALID else None,
                'sap':  yr_rt(r['SAP Score']),
                'damp': int(r.get('damp', 0)),
                'damp_rag': r.get('damp_rag', 'Green'),
                'wins': yr_rt(r.get('wins')), 'door': yr_rt(r.get('door')),
                'loft': yr_rt(r.get('loft')), 'cwi':  yr_rt(r.get('cwi')),
                'ewi':  yr_rt(r.get('ewi')),
            }
            # Only include if has any relevant data
            has_data = (entry.get('epc') in {'D','E','F','G'} or
                       any(entry.get(k) and entry[k] <= 2030
                           for k in ['wins','door','loft','cwi','ewi']) or
                       entry.get('damp', 0) > 0)
            if has_data:
                entry = {k: v for k, v in entry.items()
                         if v is not None and v != 0
                         or k in ('uprn','addr','epc','damp','damp_rag')}
                rows.append(entry)
        if rows:
            rt_prop_lookup[ag] = rows
    print(f'  Retrofit prop lookup: {sum(len(v) for v in rt_prop_lookup.values()):,} properties across {len(rt_prop_lookup)} AGs')

# Merge ag_retrofit fields into ag_epc so JS has one place to look
for ag in ag_epc:
    if ag in ag_retrofit_summary:
        ag_epc[ag].update(ag_retrofit_summary[ag])

# Also add damp data into ag_data
try:
    df_damp_ag = pd.read_excel(RAG_FILE, sheet_name='Damp & Mould Assessment', header=1)
    for _, row in df_damp_ag.iterrows():
        ag = row.get('Asset Group')
        if ag and ag in ag_epc:
            ag_epc[ag]['damp_rag']    = str(row.get('Damp RAG', 'Green'))
            ag_epc[ag]['pct_damp']    = float(row.get('% w/ 1+ Damp Repairs', 0) or 0)
            ag_epc[ag]['damp_orders'] = int(row.get('Total Damp Work Orders', 0) or 0)
    print(f'  Damp data merged into ag_data: {len(df_damp_ag)} rows')
except Exception as e:
    print(f'  WARNING: Could not merge damp data: {e}')

# Verify merge worked
sample_ag = list(ag_epc.keys())[0]
sample_val = ag_epc[sample_ag]
print(f'  Sample ag_data entry: {sample_ag[:50]}')
print(f'  Fields: {list(sample_val.keys())}')
print(f'  pct_win: {sample_val.get("pct_win","MISSING")} pct_door: {sample_val.get("pct_door","MISSING")}')
print(f'  AGs with pct_win>0: {sum(1 for v in ag_epc.values() if v.get("pct_win",0)>0)}')

retrofit_data_out = {
    'ag_data':     ag_epc,
    'ag_retrofit': ag_retrofit_summary,
    'prop_lookup': rt_prop_lookup,
}
print(f'  EPC data: {len(ag_epc)} asset groups')
print(f'  Retrofit summary: {len(ag_retrofit_summary)} asset groups')


# ── Step 9c: Top 10 worst properties ─────────────────────────────────────────
banner('STEP 9c — Top 10 worst properties')

try:
    DAMP_WPR_T10 = {'DPC','DPR','PSO'}
    DAMP_KW_T10  = ['damp','mould','mold','condensation','moisture','water pen',
                    'penetrating','rising damp','water ingress']

    df_r_t10 = pd.read_parquet(CACHE_REPAIRS)
    df_r_t10['_key'] = df_r_t10['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')

    def is_damp_t10(row):
        if str(row['WPR_Code']) in DAMP_WPR_T10: return True
        return any(kw in str(row['13_Works_Order_Description']).lower() for kw in DAMP_KW_T10)
    df_r_t10['is_damp'] = df_r_t10.apply(is_damp_t10, axis=1)

    damp_cnt  = df_r_t10[df_r_t10['is_damp']].groupby('_key').size().reset_index(name='damp_repairs')
    total_cnt = df_r_t10.groupby('_key').size().reset_index(name='total_repairs')

    CAT_KW_T10 = {
        'roof':      ['roof','roofing','flat roof','felt','fascia','gutter'],
        'window':    ['window','glazing','double glaz'],
        'kitchen':   ['kitchen','worktop','sink unit'],
        'bathroom':  ['bathroom','bath','shower','toilet','basin'],
        'electrical':['rewire','wiring','electrical','socket','consumer unit'],
        'heating':   ['boiler','heating','radiator'],
    }
    for cat, kws in CAT_KW_T10.items():
        mask = df_r_t10['13_Works_Order_Description'].str.lower().str.contains(
            '|'.join(kws), na=False)
        cc = df_r_t10[mask].groupby('_key').size().reset_index(name=f'{cat}_r')
        total_cnt = total_cnt.merge(cc, on='_key', how='left')
        total_cnt[f'{cat}_r'] = total_cnt[f'{cat}_r'].fillna(0).astype(int)

    if os.path.exists(CACHE_REP):
        df_rep_t10 = pd.read_parquet(CACHE_REP)
        df_rep_t10['_key'] = df_rep_t10['UPRN'].str.strip().str.lstrip('0')
        df_rep_t10['Year_Due_Int'] = pd.to_numeric(df_rep_t10['Year Due'], errors='coerce')
        DAMP_COMPS_T10 = {
            'Damp and Mould Growth':'damp_due','Loft Insulation':'loft_due',
            'Cavity Wall Insulation':'cwi_due','Solid Wall Insulation':'ewi_due',
            'Window Type':'window_due','External Wall Finish':'ewi_due',
        }
        df_rep_t10['comp_cat'] = df_rep_t10['Component'].map(DAMP_COMPS_T10)
        comp_min_t10 = (df_rep_t10[df_rep_t10['comp_cat'].notna()]
                        .groupby(['_key','comp_cat'])['Year_Due_Int'].min().reset_index())
        comp_piv_t10 = comp_min_t10.pivot(index='_key', columns='comp_cat',
                                          values='Year_Due_Int').reset_index()
        comp_piv_t10.columns.name = None
    else:
        comp_piv_t10 = pd.DataFrame(columns=['_key'])

    df_t10 = master[['Property Ref (UPRN)','Address','Postcode','Ward',
                      'Asset Group','EPC Rating','_key']].copy()
    df_t10 = df_t10.merge(damp_cnt, on='_key', how='left')
    df_t10 = df_t10.merge(total_cnt, on='_key', how='left')
    df_t10 = df_t10.merge(comp_piv_t10, on='_key', how='left')

    rag_cols_t10 = ['RAG_Damp_Mould','RAG_Bathroom','RAG_Kitchen',
                    'RAG_Roof','RAG_Door','RAG_Window']
    avail_rag = [c for c in rag_cols_t10 if c in df_prop.columns]
    if avail_rag:
        df_prop_t10 = df_prop.copy()
        if '_key' not in df_prop_t10.columns:
            df_prop_t10['_key'] = df_prop_t10['Property Ref (UPRN)'].str.strip().str.lstrip('0')
        df_t10 = df_t10.merge(df_prop_t10[['_key'] + avail_rag], on='_key', how='left')

    df_t10['damp_repairs'] = df_t10['damp_repairs'].fillna(0).astype(int)
    df_t10['total_repairs'] = df_t10['total_repairs'].fillna(0).astype(int)

    def rag_pts(x): return 2 if x=='Red' else 1 if x=='Amber' else 0
    df_t10['rag_pts'] = sum(
        df_t10[c].apply(rag_pts) * (3 if c=='RAG_Damp_Mould' else 1)
        for c in avail_rag if c in df_t10.columns
    )

    def comp_pts(row):
        return sum(1 for col in ['damp_due','loft_due','cwi_due','ewi_due','window_due']
                   if pd.notna(row.get(col)) and row.get(col,9999) <= 2030)
    df_t10['comp_pts'] = df_t10.apply(comp_pts, axis=1)
    df_t10['score'] = (df_t10['damp_repairs'] * 3 +
                       df_t10['rag_pts'] +
                       df_t10['comp_pts'] +
                       df_t10['total_repairs'] * 0.1)

    EPC_VALID_T10 = set('ABCDEFG')
    top10_list = []
    for _, r in df_t10.nlargest(10, 'score').iterrows():
        def yr(v):
            try: return int(float(v)) if pd.notna(v) else None
            except: return None
        top10_list.append({
            'uprn':  r['Property Ref (UPRN)'],
            'addr':  r['Address'],
            'post':  r['Postcode'],
            'ward':  r['Ward'],
            'ag':    r['Asset Group'],
            'epc':   r['EPC Rating'] if r['EPC Rating'] in EPC_VALID_T10 else None,
            'damp':  int(r['damp_repairs']),
            'total': int(r['total_repairs']),
            'roof_r': int(r.get('roof_r',0)),
            'win_r':  int(r.get('window_r',0)),
            'kit_r':  int(r.get('kitchen_r',0)),
            'bath_r': int(r.get('bathroom_r',0)),
            'elec_r': int(r.get('electrical_r',0)),
            'heat_r': int(r.get('heating_r',0)),
            'damp_rag':  str(r.get('RAG_Damp_Mould','Green')),
            'bath_rag':  str(r.get('RAG_Bathroom','Green')),
            'kit_rag':   str(r.get('RAG_Kitchen','Green')),
            'score': round(float(r['score']),1),
            'damp_due':   yr(r.get('damp_due')),
            'loft_due':   yr(r.get('loft_due')),
            'cwi_due':    yr(r.get('cwi_due')),
            'ewi_due':    yr(r.get('ewi_due')),
            'window_due': yr(r.get('window_due')),
        })

    top10_json = json.dumps(top10_list)
    print(f'  Top 10 built: {len(top10_list)} properties')
    for p in top10_list[:3]:
        print(f'    {p["addr"]}: damp={p["damp"]} total={p["total"]} score={p["score"]}')

except Exception as e:
    top10_json = '[]'
    print(f'  WARNING: Could not build top 10: {e}')


# ── Step 9d: Programme Builder data ──────────────────────────────────────────
banner('STEP 9d — Building programme data')

PROG_YEARS    = ['2026/27','2027/28','2028/29','2029/30','2030/31']
BUNDLE_YEARS  = 2   # bundle components within 2 years of earliest
COSTS_FILE    = BASE + r'\Data\Costs\HbH_Component_Costs.xlsx'

# Component name mapping: Keystone component -> cost sheet row name
COMP_COST_MAP = {
    'Bathroom Primary':           'Bathroom',
    'Kitchen':                    'Kitchen',
    'Wiring':                     'Rewiring (Wiring)',
    'Primary Heating System':     'Boiler / Primary Heating',
    'Heat Distribution':          'Heat Distribution',
    'Window Type':                'Window Type',
    'Private Front Entrance Door':'Private Front Entrance Door',
    'Pitched Roof Covering':      'Pitched Roof Covering',
    'Flat Roof Covering':         'Flat Roof Covering',
    'Loft Insulation':            'Loft Insulation',
    'Cavity Wall Insulation':     'Solid Wall Insulation (EWI)',
    'Solid Wall Insulation':      'Solid Wall Insulation (EWI)',
    'External Wall Finish':       'Solid Wall Insulation (EWI)',
    'Damp and Mould Growth':      'Damp and Mould Treatment',
}

# Default costs if no Excel file
DEFAULT_COSTS = {
    'Bathroom':                    4500,
    'Kitchen':                     5200,
    'Rewiring (Wiring)':           3500,
    'Boiler / Primary Heating':    2800,
    'Heat Distribution':           1200,
    'Window Type':                 3200,
    'Private Front Entrance Door':  850,
    'Pitched Roof Covering':       4500,
    'Flat Roof Covering':          3800,
    'Loft Insulation':             1400,
    'Cavity Wall Insulation':      1800,
    'Solid Wall Insulation (EWI)': 8500,
    'Damp and Mould Treatment':    2200,
}
DEFAULT_BUDGETS = {
    '2026/27': 2000000, '2027/28': 2500000,
    '2028/29': 2500000, '2029/30': 3000000, '2030/31': 3000000,
}
DEFAULT_INFL = 0.035

# Load costs from Excel if available
unit_costs  = dict(DEFAULT_COSTS)
budgets     = dict(DEFAULT_BUDGETS)
infl_rates  = {k: DEFAULT_INFL for k in DEFAULT_COSTS}

if os.path.exists(COSTS_FILE):
    try:
        cost_df = pd.read_excel(COSTS_FILE, sheet_name='Component Costs',
                                header=4, usecols='A:E')
        cost_df.columns = ['component','category','unit','base_cost','infl_rate']
        cost_df = cost_df.dropna(subset=['component','base_cost'])
        for _, r in cost_df.iterrows():
            unit_costs[r['component']] = float(r['base_cost'])
            infl_rates[r['component']] = float(r['infl_rate'])
        budget_df = pd.read_excel(COSTS_FILE, sheet_name='Annual Budgets',
                                  header=3, usecols='A:B')
        budget_df.columns = ['year','budget']
        budget_df = budget_df.dropna(subset=['year','budget'])
        for _, r in budget_df.iterrows():
            budgets[str(r['year'])] = float(r['budget'])
        print(f'  Costs loaded from Excel: {len(unit_costs)} components')
        print(f'  Budgets: {budgets}')
    except Exception as e:
        print(f'  WARNING: Could not load costs file: {e} — using defaults')
else:
    print(f'  No costs file found at {COSTS_FILE} — using default costs')
    print(f'  To customise: save HbH_Component_Costs.xlsx to Data\\Costs\\')

# Build programme allocation
# For each property: get all components due, group by year, apply bundling
if os.path.exists(CACHE_REP):
    df_rep_prog = pd.read_parquet(CACHE_REP)
    df_rep_prog['_key'] = df_rep_prog['UPRN'].str.strip().str.lstrip('0')
    df_rep_prog['Year_Due_Int'] = pd.to_numeric(df_rep_prog['Year Due'], errors='coerce')
    key_to_ag_prog = master.set_index('_key')['Asset Group'].to_dict()
    df_rep_prog['Asset_Group'] = df_rep_prog['_key'].map(key_to_ag_prog)

    # Filter to components we have costs for
    df_rep_prog['cost_name'] = df_rep_prog['Component'].map(COMP_COST_MAP)
    prog_data = df_rep_prog[
        df_rep_prog['cost_name'].notna() &
        df_rep_prog['Year_Due_Int'].notna() &
        df_rep_prog['Year_Due_Int'].between(2024, 2032)
    ].copy()

    # Get min year due per property per component
    prop_comp_min = prog_data.groupby(['_key','cost_name'])['Year_Due_Int'].min().reset_index()
    prop_comp_min.columns = ['_key','cost_name','year_due']
    prop_comp_min['Asset_Group'] = prop_comp_min['_key'].map(key_to_ag_prog)

    # Assign programme year with bundling
    # Map calendar year to programme year
    def cal_to_prog(yr):
        if yr <= 2027: return '2026/27'
        if yr <= 2028: return '2027/28'
        if yr <= 2029: return '2028/29'
        if yr <= 2030: return '2029/30'
        return '2030/31'

    # For each property: find earliest component due,
    # bundle any component within BUNDLE_YEARS of that
    prop_comp_min['prog_year'] = prop_comp_min['year_due'].apply(cal_to_prog)

    # Apply bundling: for each property, find min year across all components
    prop_min_year = prop_comp_min.groupby('_key')['year_due'].min().reset_index()
    prop_min_year.columns = ['_key','min_year']
    prop_comp_min = prop_comp_min.merge(prop_min_year, on='_key', how='left')

    # Bundle: if within BUNDLE_YEARS of the property's earliest component, bring forward
    prop_comp_min['bundled_year'] = prop_comp_min.apply(
        lambda r: r['min_year'] if r['year_due'] - r['min_year'] <= BUNDLE_YEARS
        else r['year_due'], axis=1)
    prop_comp_min['prog_year_final'] = prop_comp_min['bundled_year'].apply(cal_to_prog)

    # Aggregate to AG level for each programme year
    # For each AG + prog_year + component: count properties due, calculate cost
    def get_cost(comp_name, prog_year):
        base = unit_costs.get(comp_name, 3000)
        yr_idx = PROG_YEARS.index(prog_year) + 1
        infl = infl_rates.get(comp_name, DEFAULT_INFL)
        return round(base * ((1 + infl) ** yr_idx))

    programme_data = {}  # {prog_year: {ag: {comp: {props, cost_per_prop, total_cost}}}}

    for prog_year in PROG_YEARS:
        yr_data = prog_data[prog_data['_key'].isin(
            prop_comp_min[prop_comp_min['prog_year_final']==prog_year]['_key']
        )].copy()
        programme_data[prog_year] = {}

        # Get per-AG, per-component counts for this year
        yr_comps = prop_comp_min[prop_comp_min['prog_year_final']==prog_year].copy()

        for ag, ag_grp in yr_comps.groupby('Asset_Group'):
            if pd.isna(ag): continue
            ag_comps = {}
            for comp, comp_grp in ag_grp.groupby('cost_name'):
                n_props = int(len(comp_grp['_key'].unique()))
                cpp = get_cost(comp, prog_year)
                ag_comps[comp] = {
                    'props': n_props,
                    'cost_per_prop': cpp,
                    'total_cost': n_props * cpp,
                }
            if ag_comps:
                programme_data[prog_year][ag] = {
                    'components': ag_comps,
                    'total_props': int(ag_grp['_key'].nunique()),
                    'total_cost': sum(v['total_cost'] for v in ag_comps.values()),
                }

    # Get RAG priority for each AG
    rag_priority = {}
    if 'Asset Group' in df_ag.columns:
        for _, r in df_ag.iterrows():
            ag = r.get('Asset Group')
            if ag:
                reds = sum(1 for c in ['Roof','Door','Window','Kitchen','Bathroom','Damp_Mould']
                          if r.get(f'RAG_{c}','Green')=='Red')
                ambs = sum(1 for c in ['Roof','Door','Window','Kitchen','Bathroom','Damp_Mould']
                          if r.get(f'RAG_{c}','Green')=='Amber')
                rag_priority[ag] = reds*3 + ambs

    # Sort each year's AGs by RAG priority
    prog_out = {}
    for yr in PROG_YEARS:
        yr_ags = programme_data.get(yr, {})
        sorted_ags = sorted(yr_ags.items(),
                           key=lambda x: rag_priority.get(x[0], 0),
                           reverse=True)
        prog_out[yr] = [
            {'ag': ag, **data}
            for ag, data in sorted_ags
        ]

    prog_summary = {yr: {
        'total_ags': len(prog_out[yr]),
        'total_props': sum(d['total_props'] for d in prog_out[yr]),
        'total_cost': sum(d['total_cost'] for d in prog_out[yr]),
        'budget': budgets.get(yr, 0),
        'ags': prog_out[yr]
    } for yr in PROG_YEARS}

    for yr in PROG_YEARS:
        s = prog_summary[yr]
        print(f'  {yr}: {s["total_ags"]} AGs, '
              f'{s["total_props"]:,} props, '
              f'£{s["total_cost"]/1e6:.1f}M vs budget £{s["budget"]/1e6:.1f}M')

    programme_json = json.dumps({
        'years': PROG_YEARS,
        'budgets': budgets,
        'unit_costs': unit_costs,
        'programme': prog_summary,
    })
    print(f'  Programme data: {len(programme_json)/1024:.0f} KB')
else:
    programme_json = json.dumps({'years': PROG_YEARS, 'budgets': budgets,
                                 'unit_costs': unit_costs, 'programme': {}})
    print('  WARNING: REP cache not found — programme data will be empty')


# ── Step 9e: Decent Homes Assessment ─────────────────────────────────────────
banner('STEP 9e — Decent Homes Assessment')

CURRENT_YEAR = 2025

# Component lifespans for criteria 2 and 3
C2_COMPS = {
    'Window Type':               30,
    'Private Front Entrance Door':30,
    'Pitched Roof Covering':     60,
    'Flat Roof Covering':        20,
    'Primary Heating System':    15,
    'Wiring':                    30,
    'External Wall Finish':      30,
}
C3_COMPS = {
    'Bathroom Primary': 30,
    'Kitchen':          20,
}
ALL_DH_COMPS = {**C2_COMPS, **C3_COMPS}

try:
    if os.path.exists(CACHE_REP):
        df_rep_dh = pd.read_parquet(CACHE_REP)
        df_rep_dh['_key'] = df_rep_dh['UPRN'].str.strip().str.lstrip('0')
        df_rep_dh['Year_Due_Int'] = pd.to_numeric(df_rep_dh['Year Due'], errors='coerce')

        # Get min Year Due per property per component
        dh_comps_data = df_rep_dh[df_rep_dh['Component'].isin(ALL_DH_COMPS)].copy()
        comp_min_dh = (dh_comps_data
                       .groupby(['_key','Component'])['Year_Due_Int']
                       .min().reset_index())
        comp_pivot_dh = comp_min_dh.pivot(index='_key', columns='Component',
                                          values='Year_Due_Int').reset_index()
        comp_pivot_dh.columns.name = None

        # Get damp RAG and EPC from existing data
        df_prop_dh = master[['Property Ref (UPRN)','Address','Postcode','Ward',
                             'Asset Group','Ownership Type','EPC Rating',
                             'SAP Score','_key']].copy()
        df_prop_dh['SAP_num'] = pd.to_numeric(df_prop_dh['SAP Score'], errors='coerce')
        df_prop_dh = df_prop_dh.merge(comp_pivot_dh, on='_key', how='left')

        # Get damp RAG
        if 'RAG_Damp_Mould' in df_prop.columns:
            df_prop_rag_dh = df_prop.copy()
            if '_key' not in df_prop_rag_dh.columns:
                df_prop_rag_dh['_key'] = df_prop_rag_dh['Property Ref (UPRN)'].str.strip().str.lstrip('0')
            df_prop_dh = df_prop_dh.merge(
                df_prop_rag_dh[['_key','RAG_Damp_Mould']].rename(
                    columns={'RAG_Damp_Mould':'damp_rag'}),
                on='_key', how='left')
            df_prop_dh['damp_rag'] = df_prop_dh['damp_rag'].fillna('Green')
        else:
            df_prop_dh['damp_rag'] = 'Green'

        # ── Criterion 1: HHSRS ───────────────────────────────────────────────
        # Fail if: damp RAG = Red OR EPC F/G (excess cold risk)
        df_prop_dh['c1_damp']  = df_prop_dh['damp_rag'] == 'Red'
        df_prop_dh['c1_cold']  = df_prop_dh['EPC Rating'].isin(['F','G'])
        df_prop_dh['c1_fail']  = df_prop_dh['c1_damp'] | df_prop_dh['c1_cold']

        # ── Criterion 2: State of Repair ─────────────────────────────────────
        # Fail if any C2 component is overdue (Year Due < current year)
        c2_fails = []
        for comp, lifespan in C2_COMPS.items():
            col = comp
            if col in df_prop_dh.columns:
                # Component overdue if Year Due < current year
                fail = df_prop_dh[col].notna() & (df_prop_dh[col] < CURRENT_YEAR)
                c2_fails.append(fail)
        if c2_fails:
            import functools
            df_prop_dh['c2_fail'] = functools.reduce(lambda a,b: a|b, c2_fails)
        else:
            df_prop_dh['c2_fail'] = False

        # ── Criterion 3: Modern Facilities ───────────────────────────────────
        # Kitchen fail if age > 20 yrs: install year < 2005
        # Bathroom fail if age > 30 yrs: install year < 1995
        # Install year = Year Due - lifespan
        # Age > threshold means: CURRENT_YEAR - (Year Due - lifespan) > threshold
        # i.e. Year Due < CURRENT_YEAR (just use overdue as proxy)
        df_prop_dh['c3_kitchen'] = False
        df_prop_dh['c3_bath']    = False
        if 'Kitchen' in df_prop_dh.columns:
            kitchen_install = df_prop_dh['Kitchen'] - C3_COMPS['Kitchen']
            df_prop_dh['c3_kitchen'] = (
                df_prop_dh['Kitchen'].notna() &
                (CURRENT_YEAR - kitchen_install > C3_COMPS['Kitchen'])
            )
        if 'Bathroom Primary' in df_prop_dh.columns:
            bath_install = df_prop_dh['Bathroom Primary'] - C3_COMPS['Bathroom Primary']
            df_prop_dh['c3_bath'] = (
                df_prop_dh['Bathroom Primary'].notna() &
                (CURRENT_YEAR - bath_install > C3_COMPS['Bathroom Primary'])
            )
        df_prop_dh['c3_fail'] = df_prop_dh['c3_kitchen'] | df_prop_dh['c3_bath']

        # ── Criterion 4: Thermal Comfort ─────────────────────────────────────
        # Fail if: SAP < 35 OR EPC F/G OR heating overdue with no insulation
        df_prop_dh['c4_sap']  = df_prop_dh['SAP_num'].notna() & (df_prop_dh['SAP_num'] < 35)
        df_prop_dh['c4_epc']  = df_prop_dh['EPC Rating'].isin(['F','G'])
        heat_overdue = False
        if 'Primary Heating System' in df_prop_dh.columns:
            heat_overdue = (df_prop_dh['Primary Heating System'].notna() &
                           (df_prop_dh['Primary Heating System'] < CURRENT_YEAR))
        df_prop_dh['c4_fail'] = df_prop_dh['c4_sap'] | df_prop_dh['c4_epc'] | heat_overdue

        # ── Overall Non-Decent ────────────────────────────────────────────────
        # Council is not responsible for internal components in leasehold properties
        # Criteria 2 (internal components) and 3 (kitchen/bathroom) exclude leaseholders
        # Criterion 1 (HHSRS) and 4 (thermal) apply to all tenures
        LEASEHOLDER_TENURE = 'LEASE'
        df_prop_dh['is_lease'] = df_prop_dh['Ownership Type'] == LEASEHOLDER_TENURE

        # For leaseholders: only C1 and C4 apply (council responsible for structure/thermal)
        # C2 and C3 (internal components) are leaseholder responsibility
        df_prop_dh['c2_fail_resp'] = df_prop_dh['c2_fail'] & ~df_prop_dh['is_lease']
        df_prop_dh['c3_fail_resp'] = df_prop_dh['c3_fail'] & ~df_prop_dh['is_lease']

        df_prop_dh['non_decent'] = (
            df_prop_dh['c1_fail'] |
            df_prop_dh['c2_fail_resp'] |
            df_prop_dh['c3_fail_resp'] |
            df_prop_dh['c4_fail']
        )

        # Council-responsible stock (exclude leaseholder from headline figures)
        df_council = df_prop_dh[df_prop_dh['Ownership Type'] != LEASEHOLDER_TENURE]

        total        = len(df_prop_dh)
        total_resp   = len(df_council)
        total_lease  = int(df_prop_dh['is_lease'].sum())
        non_decent_n = int(df_council['non_decent'].sum())
        non_decent_all = int(df_prop_dh['non_decent'].sum())
        c1_n = int(df_council['c1_fail'].sum())
        c2_n = int(df_council['c2_fail_resp'].sum())
        c3_n = int(df_council['c3_fail_resp'].sum())
        c4_n = int(df_council['c4_fail'].sum())

        print(f'  Total properties: {total:,}')
        print(f'    Council/GFTA (responsible): {total_resp:,}')
        print(f'    Leasehold (excluded from headline): {total_lease:,}')
        print(f'  Non-decent (council responsible): {non_decent_n:,} ({non_decent_n/total_resp*100:.1f}%)')
        print(f'  C1 (HHSRS):     {c1_n:,} ({c1_n/total_resp*100:.1f}%)')
        print(f'  C2 (Repair):    {c2_n:,} ({c2_n/total_resp*100:.1f}%)')
        print(f'  C3 (Modern):    {c3_n:,} ({c3_n/total_resp*100:.1f}%)')
        print(f'  C4 (Thermal):   {c4_n:,} ({c4_n/total_resp*100:.1f}%)')

        # ── Build per-property output ────────────────────────────────────────
        def clean_dh(v):
            try:
                if pd.isna(v): return None
            except: pass
            if isinstance(v, (bool,)): return bool(v)
            if isinstance(v, float):
                try:
                    if v == int(v): return int(v)
                except: pass
            return v

        dh_props = []
        for _, r in df_prop_dh.iterrows():
            entry = {
                'uprn':  r['Property Ref (UPRN)'],
                'addr':  r['Address'],
                'post':  r['Postcode'],
                'ward':  r['Ward'],
                'ag':    r['Asset Group'],
                'tenure':r['Ownership Type'],
                'is_lease': bool(r['is_lease']),
                'epc':   r['EPC Rating'] if r['EPC Rating'] in list('ABCDEFG') else None,
                'sap':   clean_dh(r['SAP_num']),
                'damp_rag': r['damp_rag'],
                'non_decent': bool(r['non_decent']),
                'c1': bool(r['c1_fail']),
                'c2': bool(r['c2_fail_resp']),
                'c3': bool(r['c3_fail_resp']),
                'c4': bool(r['c4_fail']),
                'c1_damp': bool(r['c1_damp']), 'c1_cold': bool(r['c1_cold']),
                'c3_kit':  bool(r['c3_kitchen']), 'c3_bath': bool(r['c3_bath']),
                # C2/C3 component Year Due values for drill-down detail
                'win_due':   int(float(r['Window Type'])) if pd.notna(r.get('Window Type')) else None,
                'door_due':  int(float(r['Private Front Entrance Door'])) if pd.notna(r.get('Private Front Entrance Door')) else None,
                'roof_due':  int(float(r['Pitched Roof Covering'])) if pd.notna(r.get('Pitched Roof Covering')) else (int(float(r['Flat Roof Covering'])) if pd.notna(r.get('Flat Roof Covering')) else None),
                'heat_due':  int(float(r['Primary Heating System'])) if pd.notna(r.get('Primary Heating System')) else None,
                'wire_due':  int(float(r['Wiring'])) if pd.notna(r.get('Wiring')) else None,
                'wall_due':  int(float(r['External Wall Finish'])) if pd.notna(r.get('External Wall Finish')) else None,
                'kit_due':   int(float(r['Kitchen'])) if pd.notna(r.get('Kitchen')) else None,
                'bath_due':  int(float(r['Bathroom Primary'])) if pd.notna(r.get('Bathroom Primary')) else None,
            }
            # Only include non-decent properties to save space
            if entry['non_decent']:
                dh_props.append({k:v for k,v in entry.items() if v is not None and v is not False
                                 or k in ('uprn','addr','non_decent','c1','c2','c3','c4')})

        # ── AG-level summary ──────────────────────────────────────────────────
        dh_ag = {}
        for ag, grp in df_prop_dh.groupby('Asset Group'):
            total_ag = len(grp)
            nd = int(grp['non_decent'].sum())
            dh_ag[ag] = {
                'total': total_ag,
                'non_decent': nd,
                'pct_nd': round(nd/total_ag*100, 1) if total_ag > 0 else 0,
                'c1': int(grp['c1_fail'].sum()),
                'c2': int(grp['c2_fail'].sum()),
                'c3': int(grp['c3_fail'].sum()),
                'c4': int(grp['c4_fail'].sum()),
            }

        # ── Ward-level summary ────────────────────────────────────────────────
        dh_ward = {}
        for ward, grp in df_prop_dh.groupby('Ward'):
            total_w = len(grp)
            nd_w = int(grp['non_decent'].sum())
            dh_ward[ward] = {
                'total': total_w,
                'non_decent': nd_w,
                'pct_nd': round(nd_w/total_w*100, 1) if total_w > 0 else 0,
                'c1': int(grp['c1_fail'].sum()),
                'c2': int(grp['c2_fail'].sum()),
                'c3': int(grp['c3_fail'].sum()),
                'c4': int(grp['c4_fail'].sum()),
            }

        # ── Tenure summary ────────────────────────────────────────────────────
        tenure_map = {'COUN':'Council Owned','LEASE':'Leasehold','GENFUNDTA':'General Fund TA'}
        dh_tenure = {}
        for tenure, grp in df_prop_dh.groupby('Ownership Type'):
            total_t = len(grp)
            nd_t = int(grp['non_decent'].sum())
            dh_tenure[tenure_map.get(tenure, tenure)] = {
                'total': total_t,
                'non_decent': nd_t,
                'pct_nd': round(nd_t/total_t*100,1) if total_t>0 else 0,
            }

        # Slim properties list - only include worst 500 to manage file size
        dh_props_slim = sorted(dh_props, key=lambda x: sum([
            x.get('c1',False)*3, x.get('c2',False)*2,
            x.get('c3',False), x.get('c4',False)
        ]), reverse=True)[:500]

        decent_homes_json = json.dumps({
            'summary': {
                'total':         total,
                'total_resp':    total_resp,
                'total_lease':   total_lease,
                'total_gfta':    int((df_prop_dh['Ownership Type']=='GENFUNDTA').sum()),
                'total_council': int((df_prop_dh['Ownership Type']=='COUN').sum()),
                'non_decent':    non_decent_n,
                'non_decent_all':non_decent_all,
                'pct_nd':        round(non_decent_n/total_resp*100, 1) if total_resp>0 else 0,
                'c1': c1_n, 'c2': c2_n, 'c3': c3_n, 'c4': c4_n,
                'assessment_year': CURRENT_YEAR,
                'note': 'Headline figures exclude leasehold properties for criteria 2 and 3 (internal components). Council is not responsible for kitchen, bathroom and boiler replacements in leasehold properties.',
            },
            'ag_data':    dh_ag,
            'ward_data':  dh_ward,
            'tenure_data':dh_tenure,
            'properties': dh_props_slim,
        })
        print(f'  Decent Homes JSON: {len(decent_homes_json)/1024:.0f} KB')
        print(f'  Non-decent properties included: {len(dh_props):,}')
    else:
        decent_homes_json = '{}'
        print('  WARNING: REP cache not found — Decent Homes data will be empty')

except Exception as e:
    decent_homes_json = '{}'
    print(f'  WARNING: Decent Homes build failed: {e}')

# ── Step 10: Read template and inject ─────────────────────────────────────────
# ── Step 9b: Damp work orders per property ───────────────────────────────────
banner('STEP 9b — Damp work orders lookup')

damp_repairs_out = {}
if os.path.exists(CACHE_REPAIRS):
    df_rep2 = pd.read_parquet(CACHE_REPAIRS)
    df_rep2['_key'] = df_rep2['50_Property_Ref'].astype(str).str.strip().str.lstrip('0')
    df_rep2['_date'] = pd.to_datetime(df_rep2['_date'], errors='coerce')
    DAMP_WPR2 = {'DPC', 'DPR', 'PSO'}
    DAMP_KW2  = ['damp', 'mould', 'mold', 'condensation', 'moisture',
                 'water pen', 'water penetration', 'penetrating', 'rising damp',
                 'water ingress']
    def is_damp2(row):
        if str(row['WPR_Code']) in DAMP_WPR2: return True
        return any(kw in str(row['13_Works_Order_Description']).lower() for kw in DAMP_KW2)
    df_rep2['is_damp2'] = df_rep2.apply(is_damp2, axis=1)
    damp_wo = df_rep2[df_rep2['is_damp2']].copy()
    for key, grp in damp_wo.groupby('_key'):
        rows = []
        for _, r in grp.sort_values('_date', ascending=False).iterrows():
            rows.append({
                'd':  str(r['13_Works_Order_Description'])[:150],
                'w':  str(r['WPR_Code']) if pd.notna(r['WPR_Code']) else '',
                'dt': r['_date'].strftime('%d/%m/%Y') if pd.notna(r['_date']) else '',
            })
        damp_repairs_out[key] = rows
    print(f'  Damp work orders: {sum(len(v) for v in damp_repairs_out.values()):,} orders across {len(damp_repairs_out):,} properties')
else:
    print('  WARNING: Repairs cache not found — work orders will be empty')

banner('STEP 10 — Injecting data into template')

with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    html = f.read()
print(f'  Template read: {len(html):,} chars')

# Inject all data using direct const replacement
html = inject(html, 'DATA',          json.dumps(portal_out))
html = inject(html, 'FY_DATA',       json.dumps(fy_totals))
html = inject(html, 'SC_DATA',       json.dumps(sc_data))
html = inject(html, 'RETROFIT',      json.dumps(retrofit_out))
html = inject(html, 'PROP_LOOKUP',   json.dumps(prop_lookup))
html = inject(html, 'BLOCK_DATA',    json.dumps(block_data_out))
html = inject(html, 'RETROFIT_DATA', json.dumps(retrofit_data_out))
html = inject(html, 'DAMP_REPAIRS',   json.dumps(damp_repairs_out))
html = inject(html, 'TOP10_WORST',    top10_json)
html = inject(html, 'PROGRAMME_DATA', programme_json)
html = inject(html, 'DECENT_HOMES',   decent_homes_json)

print(f'\n  Output size: {len(html):,} chars ({len(html)/1024:.0f} KB)')

# Write output
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(html)

banner('PORTAL BUILD COMPLETE')
print(f'  Output: {OUTPUT_FILE}')
print(f'  Size:   {len(html)/1024:.0f} KB ({len(html)/1024/1024:.1f} MB)')
print(f'\n  Open HbH_Portal.html in Chrome to view the portal.')
