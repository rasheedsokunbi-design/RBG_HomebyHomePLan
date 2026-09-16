"""
run_llm_categoriser.py
======================
One-off LLM categorisation step for the Home by Home Plan pipeline.

Reads the repairs cache, strips PII, deduplicates descriptions,
sends unique descriptions to GPT-5.6 Luna via OpenAI (concurrently),
and saves results to Data\\Cache\\llm_categories.parquet.

Usage:
    Set OPENAI_API_KEY environment variable then run:
    python run_llm_categoriser.py
"""

import os, re, sys, json, time, random, asyncio, logging
import pandas as pd
from typing import Optional, List
from pydantic import BaseModel
import enum

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_API_KEY  = os.environ.get('OPENAI_API_KEY', 'YOUR_API_KEY_HERE')
MODEL_NAME      = 'gpt-5.6-luna'
BASE            = r'G:\Shared drives\DG Cities\Projects\HomeByHomePlatform\HTML_Prototype'
CACHE_REPAIRS   = os.path.join(BASE, r'Data\Cache\cache_repairs.parquet')
LLM_CACHE       = os.path.join(BASE, r'Data\Cache\llm_categories.parquet')
CHUNK_SIZE      = 20   # descriptions per API call
MAX_CONCURRENCY = 20   # simultaneous API calls
MAX_RETRIES     = 3

# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class Category(enum.Enum):
    LEAK='Leak'; ELECTRICAL='Electrical'; PLUMBING='Plumbing'
    DAMP='Damp'; DOOR_WINDOW='Door/Window'; HEATING_HW='Heating/Hot Water'
    ROOF='Roof'; STRUCTURAL_WALL='Structural/Wall'; ACCESSIBILITY='Accessibility'
    ASBESTOS='Asbestos'; FENCE_GARDEN='Fence/Garden'; PEST_CONTROL='Pest Control'
    VACANCY='Vacancy'; KITCHEN='Kitchen'; BATHROOM='Bathroom'; OTHER='Other'

class Cause(enum.Enum):
    ROOF='Roof'; PLUMBING='Plumbing'; UNKNOWN='Unknown'

class Impact(enum.Enum):
    STRUCTURAL_WALL='Structural/Wall'; DAMP='Damp'
    ELECTRICAL='Electrical'; DOOR_WINDOW='Door/Window'

class Scale(enum.Enum):
    MINOR='Minor'; MAJOR='Major'; UNKNOWN='Unknown'

class RepairLog(BaseModel):
    log_index: int
    category:  Category
    cause:     Optional[Cause]  = None
    impact:    Optional[Impact] = None
    scale:     Scale

class RepairLogsResponse(BaseModel):
    results: List[RepairLog]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY MAPPING
# ─────────────────────────────────────────────────────────────────────────────

LLM_TO_RAG = {
    'Leak':'Damp & Mould', 'Damp':'Damp & Mould',
    'Electrical':'Electrical', 'Plumbing':'Bathroom',
    'Door/Window':'Window', 'Heating/Hot Water':'Heating',
    'Roof':'Roof', 'Structural/Wall':'Roof',
    'Kitchen':'Kitchen', 'Bathroom':'Bathroom',
    'Accessibility':'Other','Asbestos':'Other',
    'Fence/Garden':'Other','Pest Control':'Other',
    'Vacancy':'Other','Other':'Other',
}

# ─────────────────────────────────────────────────────────────────────────────
# PII STRIPPING
# ─────────────────────────────────────────────────────────────────────────────

def strip_pii(text):
    if not isinstance(text, str): return str(text)
    text = re.sub(r'\b07\d{3}[\s\-]?\d{6}\b', '[NUMBER REMOVED]', text)
    text = re.sub(r'\b0[123]\d{2,3}[\s\-]?\d{5,6}\b', '[NUMBER REMOVED]', text)
    text = re.sub(r'\b\d{11}\b', '[NUMBER REMOVED]', text)
    text = re.sub(r'\+44[\s\-]?\d{4}[\s\-]?\d{6}\b', '[NUMBER REMOVED]', text)
    return text.strip()

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────────────────────────

MAIN_CATEGORIES = [
    'Electrical','Plumbing','Damp','Door/Window','Heating/Hot Water',
    'Roof','Structural/Wall','Accessibility','Asbestos','Fence/Garden',
    'Pest Control','Vacancy','Kitchen','Bathroom','Other'
]

ONE_SHOT = """Input:
1. No HTG/HW
2. make saf lights in kitchen and bathroom due to water penetrating through ceiling from leak in above flat
3. Fco - Reinstate when dry
4. Install two 42mm galvanized hand rails pocketed into hard standing
5. replace flue seals
6. Tnt lost her key and locked out.
7. Collect dehum and return to Lakedale
8. PSO to inspect tree in back garden affecting neighbour area.
9. Make good timber/painting above kitchen and bathroom window.

Output:
1. {"log_index": 1, "category": "Heating/Hot Water", "scale": "Unknown"}
2. {"log_index": 2, "category": "Leak", "cause": "Plumbing", "impact": "Electrical", "scale": "Major"}
3. {"log_index": 3, "category": "Plumbing", "scale": "Minor"}
4. {"log_index": 4, "category": "Accessibility", "scale": "Unknown"}
5. {"log_index": 5, "category": "Heating/Hot Water", "scale": "Minor"}
6. {"log_index": 6, "category": "Door/Window", "scale": "Minor"}
7. {"log_index": 7, "category": "Damp", "scale": "Minor"}
8. {"log_index": 8, "category": "Fence/Garden", "scale": "Unknown"}
9. {"log_index": 9, "category": "Door/Window", "scale": "Minor"}"""

SYSTEM_PROMPT = f"""You are a property repair categorization assistant. Categorize each repair log entry using the process below and return strict JSON only.

## Decision Process
1. **Is it a leak?** (keywords: leak, water penetration, flood, burst pipe, water dripping)
   - Yes → assign category "Leak", then determine:
     - cause: "Roof" (from roof/gutters) | "Plumbing" (internal pipes/taps/toilets) | "Unknown"
     - impact: "Structural/Wall" | "Damp" | "Door/Window" | "Electrical"
   - No → assign one of: {MAIN_CATEGORIES}

2. **Scale** (all entries):
   - "Minor" – completable in one day; simple part swaps
   - "Major" – multi-day; full replacements
   - "Unknown" – scale unclear

## Rules
- Output JSON only, no reasoning, in input order.
- Output list must be same length as input list.
- Prioritize functional category over room: electrical fault in kitchen → "Electrical" not "Kitchen".
- "Kitchen"/"Bathroom" only for room-specific works (fitting cabinets, re-tiling).
- Gutter issues → "Roof". Fan/ventilation/condensation → "Damp".
- DPC, DPR, PSO codes → "Damp". [NUMBER REMOVED] = stripped phone number, ignore it.

## Example
{ONE_SHOT}"""

# ─────────────────────────────────────────────────────────────────────────────
# ASYNC API CALLS
# ─────────────────────────────────────────────────────────────────────────────

def parse_result(r):
    """Safely extract string value from enum or string."""
    if r is None: return None
    if isinstance(r, dict): return r.get('value', str(r))
    if hasattr(r, 'value'): return r.value
    return str(r)

async def call_chunk_async(client, semaphore, chunk, chunk_idx,
                           start_idx, progress):
    """Send one chunk to OpenAI asynchronously."""
    async with semaphore:
        lines = ['Categorize these repair logs and return a JSON list in the exact same order:\n']
        for i, desc in enumerate(chunk, start_idx):
            lines.append(f'{i}. {desc}')
        user_msg = '\n'.join(lines)

        for attempt in range(MAX_RETRIES + 1):
            try:
                completion = await client.beta.chat.completions.parse(
                    model=MODEL_NAME,
                    messages=[
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user',   'content': user_msg},
                    ],
                    response_format=RepairLogsResponse,
                )
                result = completion.choices[0].message.parsed
                if len(result.results) != len(chunk):
                    raise ValueError(f'Expected {len(chunk)}, got {len(result.results)}')

                results = []
                for desc, r in zip(chunk, result.results):
                    cat = parse_result(r.category)
                    results.append({
                        'description':    desc,
                        'llm_category':   cat,
                        'llm_scale':      parse_result(r.scale),
                        'llm_leak_cause': parse_result(r.cause),
                        'llm_leak_impact':parse_result(r.impact),
                        'rag_category':   LLM_TO_RAG.get(cat, 'Other'),
                    })
                progress['done'] += len(chunk)
                return results

            except Exception as e:
                if attempt >= MAX_RETRIES:
                    # Fallback: mark all as Other
                    progress['done'] += len(chunk)
                    progress['failed'] += len(chunk)
                    return [{
                        'description': desc, 'llm_category': 'Other',
                        'llm_scale': 'Unknown', 'llm_leak_cause': None,
                        'llm_leak_impact': None, 'rag_category': 'Other',
                    } for desc in chunk]
                wait = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(wait)


async def run_async(new_descs, client):
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    chunks = [new_descs[i:i+CHUNK_SIZE]
              for i in range(0, len(new_descs), CHUNK_SIZE)]
    total = len(chunks)
    progress = {'done': 0, 'failed': 0}
    start = time.time()

    tasks = [
        call_chunk_async(client, semaphore, chunk,
                         idx, idx*CHUNK_SIZE+1, progress)
        for idx, chunk in enumerate(chunks)
    ]

    # Print progress while running
    async def print_progress():
        while progress['done'] < len(new_descs):
            elapsed = time.time() - start
            pct = progress['done'] / len(new_descs) * 100
            rate = progress['done'] / elapsed if elapsed > 0 else 1
            eta  = (len(new_descs) - progress['done']) / rate if rate > 0 else 0
            print(f'\r  Progress: {progress["done"]:>6,}/{len(new_descs):,} '
                  f'({pct:.1f}%) — {elapsed/60:.1f}m elapsed, '
                  f'~{eta/60:.1f}m remaining    ', end='', flush=True)
            await asyncio.sleep(2)

    progress_task = asyncio.create_task(print_progress())
    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
    progress_task.cancel()
    print()  # newline after progress

    # Flatten results
    all_results = []
    for res in chunk_results:
        if isinstance(res, Exception):
            continue
        if res:
            all_results.extend(res)
    return all_results

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def banner(msg):
    print('\n' + '='*60)
    print(f'  {msg}')
    print('='*60)

def main():
    banner('LLM REPAIR CATEGORISER — Home by Home Plan')

    if not OPENAI_API_KEY or OPENAI_API_KEY == 'YOUR_API_KEY_HERE':
        print('ERROR: Set OPENAI_API_KEY environment variable.')
        sys.exit(1)

    banner('STEP 1 — Loading repairs cache')
    if not os.path.exists(CACHE_REPAIRS):
        print(f'ERROR: Not found: {CACHE_REPAIRS}')
        print('Run run_all.py with REBUILD_CACHE = True first.')
        sys.exit(1)

    df = pd.read_parquet(CACHE_REPAIRS)
    print(f'  Loaded {len(df):,} repair records')

    banner('STEP 2 — Checking existing cache')
    existing_descs = set()
    df_existing = pd.DataFrame()
    if os.path.exists(LLM_CACHE):
        df_existing = pd.read_parquet(LLM_CACHE)
        existing_descs = set(df_existing['description'].unique())
        print(f'  Already cached: {len(existing_descs):,} unique descriptions')
    else:
        print('  No existing cache — starting fresh')

    banner('STEP 3 — PII stripping & deduplication')
    desc_col = '13_Works_Order_Description'
    df['desc_clean'] = df[desc_col].apply(strip_pii)
    all_descs  = [d for d in df['desc_clean'].dropna().unique() if d]
    new_descs  = [d for d in all_descs if d not in existing_descs]
    print(f'  Total unique descriptions:   {len(all_descs):,}')
    print(f'  Already in cache:            {len(existing_descs):,}')
    print(f'  New to process:              {len(new_descs):,}')

    if not new_descs:
        print('\n  Nothing to do — all descriptions already cached.')
        return

    # Cost estimate
    est_input  = len(new_descs) * 25  / 1_000_000
    est_output = len(new_descs) * 20  / 1_000_000
    est_usd    = est_input * 0.10 + est_output * 0.60
    est_gbp    = est_usd * 0.79
    n_chunks   = len(new_descs) // CHUNK_SIZE + 1
    est_mins   = n_chunks / MAX_CONCURRENCY * 0.5  # rough estimate

    print(f'\n  Estimated cost:  ${est_usd:.2f} USD / £{est_gbp:.2f} GBP')
    print(f'  Model:           {MODEL_NAME}')
    print(f'  Concurrency:     {MAX_CONCURRENCY} simultaneous calls')
    print(f'  Est. time:       ~{est_mins:.0f} minutes')

    confirm = input('\n  Proceed? (yes/no): ').strip().lower()
    if confirm not in ('yes', 'y'):
        print('  Aborted.')
        return

    banner('STEP 4 — Categorising with GPT-5.6 Luna (async)')
    try:
        import openai
        async_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        print('ERROR: pip install openai pydantic')
        sys.exit(1)

    start = time.time()
    results = asyncio.run(run_async(new_descs, async_client))
    elapsed = time.time() - start
    print(f'\n  Done: {len(results):,} descriptions in {elapsed/60:.1f} minutes')

    banner('STEP 5 — Saving cache')
    df_results = pd.DataFrame(results)

    # Show distribution
    print('\n  Category distribution:')
    for cat, n in df_results['llm_category'].value_counts().items():
        rag = LLM_TO_RAG.get(cat, 'Other')
        print(f'    {cat:<25} {n:>6,}  →  {rag}')

    if len(df_existing) > 0:
        df_combined = pd.concat([df_existing, df_results], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=['description'], keep='last')
    else:
        df_combined = df_results

    os.makedirs(os.path.dirname(LLM_CACHE), exist_ok=True)
    df_combined.to_parquet(LLM_CACHE, index=False)
    print(f'\n  Saved {len(df_combined):,} descriptions to:')
    print(f'  {LLM_CACHE}')

    banner('COMPLETE')
    print(f'  Run run_all.py to rebuild the portal with LLM categories.')

if __name__ == '__main__':
    main()
