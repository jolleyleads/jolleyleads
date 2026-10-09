import os, time, json, re, threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus, urlparse
from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 262144
VERSION = '2026.10.09.1'
CATEGORIES = ('all', 'court', 'business', 'genealogy')
SOURCES = [
 ('CourtListener', 'Court opinions; independent nonprofit archive', 'https://www.courtlistener.com/?q={q}', 'court'),
 ('PACER', 'Official federal dockets; account and fees may apply', 'https://pacer.uscourts.gov/', 'court'),
 ('SEC EDGAR', 'Official public-company filings', 'https://www.sec.gov/edgar/search/#/q={q}', 'business'),
 ('USAspending', 'Official federal awards and spending', 'https://www.usaspending.gov/search', 'business'),
 ('National Archives', 'Official historical government records', 'https://catalog.archives.gov/search?q={q}', 'genealogy'),
 ('Library of Congress', 'Official historical collections; not a complete genealogy index', 'https://www.loc.gov/search/?q={q}', 'genealogy'),
 ('FamilySearch', 'Independent genealogy provider; account may be required', 'https://www.familysearch.org/search/', 'genealogy'),
 ('Ancestry', 'Independent genealogy provider; subscription may be required', 'https://www.ancestry.com/', 'genealogy'),
 ('NARA Census', 'Official historical census research', 'https://www.archives.gov/research/census', 'genealogy'),
 ('State court directory', 'National Center for State Courts directory', 'https://www.ncsc.org/information-and-resources/state-court-websites', 'court'),
 ('State business registries', 'Secretary of State directory; registrations vary by state', 'https://www.nass.org/business-services/corporate-registration', 'business'),
]
CACHE = {}
CACHE_LOCK = threading.Lock()

def now():
 return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def get_json(url, params=None, headers=None):
 # Only connectors below supply URLs, never caller-controlled destinations.
 key = (url, json.dumps(params or {}, sort_keys=True))
 with CACHE_LOCK:
  hit = CACHE.get(key)
  if hit and time.monotonic() - hit[0] < 60:
   return hit[1]
 response = requests.get(url, params=params, headers=headers, timeout=8)
 response.raise_for_status()
 value = response.json()
 with CACHE_LOCK:
  if len(CACHE) >= 100:
   CACHE.clear()
  CACHE[key] = (time.monotonic(), value)
 return value

def record(title, description, url, category, source):
 return dict(title=str(title)[:250], description=str(description)[:600], url=url,
             category=category, source=source, status='api_result', verified_record=False,
             provenance='Retrieved from source; identity and accuracy require review')

def allowed_url(url, host):
 parsed = urlparse(str(url))
 return parsed.scheme == 'https' and parsed.hostname in (host, 'www.' + host)

def sec_search(q):
 user_agent = os.getenv('SEC_USER_AGENT')
 if not user_agent:
  return [], 'not_configured', 'Direct SEC retrieval needs a configured SEC_USER_AGENT contact header. Official EDGAR links are available.'
 headers = {'User-Agent': user_agent, 'Accept': 'application/json'}
 if re.fullmatch(r'(?:CIK\s*)?\d{1,10}', q, re.I):
  cik = int(re.sub(r'(?i)CIK\s*', '', q))
  companies = [{'cik_str': cik, 'title': 'CIK ' + str(cik), 'ticker': ''}]
 else:
  data = get_json('https://www.sec.gov/files/company_tickers.json', headers=headers)
  companies = [c for c in data.values() if q.casefold() in str(c.get('title', '')).casefold() or q.casefold() == str(c.get('ticker', '')).casefold()][:5]
 items = []
 for company in companies:
  cik = int(company['cik_str'])
  items.append(record(str(company['title']) + (' (' + company['ticker'] + ')' if company['ticker'] else ''),
                      'Company directory · CIK ' + str(cik), 'https://www.sec.gov/edgar/browse/?CIK=' + str(cik), 'business', 'SEC EDGAR'))
 # Bound requests: retrieve filings for the first matching company only.
 if companies:
  cik = int(companies[0]['cik_str'])
  data = get_json(f'https://data.sec.gov/submissions/CIK{cik:010d}.json', headers=headers)
  recent = data.get('filings', {}).get('recent', {})
  for i, accession in enumerate(recent.get('accessionNumber', [])[:10]):
   document = recent.get('primaryDocument', [])[i]
   if not re.fullmatch(r'[\w.-]+', document) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession):
    continue
   url = f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace("-", "")}/{document}'
   items.append(record(data.get('name', companies[0]['title']) + ' · ' + recent['form'][i],
                       'Filed ' + recent['filingDate'][i] + ' · accession ' + accession, url, 'business', 'SEC EDGAR'))
 return items

def loc_search(q):
 data = get_json('https://www.loc.gov/search/', params={'q': q, 'fo': 'json', 'c': 15})
 if not isinstance(data.get('results'), list):
  raise ValueError('Invalid Library of Congress response')
 items = []
 for item in data['results']:
  url = item.get('url') or item.get('id', '')
  if not allowed_url(url, 'loc.gov'):
   continue
  description = item.get('description', [])
  if isinstance(description, list):
   description = ' '.join(str(x) for x in description)
  items.append(record(item.get('title', 'Historical collection item'), str(item.get('date', '')) + ' · ' + str(description), url, 'genealogy', 'Library of Congress'))
 return items

def court_search(q):
 token = os.getenv('COURTLISTENER_API_TOKEN')
 if not token:
  return [], 'not_configured', 'CourtListener record search needs an API token. Court source links are available.'
 data = get_json('https://www.courtlistener.com/api/rest/v4/search/', params={'q': q, 'type': 'o', 'order_by': 'dateFiled desc'}, headers={'Authorization': 'Token ' + token})
 if not isinstance(data.get('results'), list):
  raise ValueError('Invalid CourtListener response')
 items = []
 for item in data['results'][:15]:
  path = item.get('absolute_url', '')
  if not path.startswith('/') or path.startswith('//'):
   continue
  items.append(record(item.get('caseName', 'Court opinion'), str(item.get('court', '')) + ' · ' + str(item.get('dateFiled', '')) + ' · docket ' + str(item.get('docketNumber', '')), 'https://www.courtlistener.com' + path, 'court', 'CourtListener'))
 return items, 'ok', None

def connector(name, fn, q):
 try:
  result = fn(q)
  if isinstance(result, tuple):
   items, status, message = result
  else:
   items, status, message = result, 'ok', None
  return items, dict(source=name, status=status, count=len(items), message=message)
 except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
  return [], dict(source=name, status='unavailable', count=0, message=name + ' is unavailable. No successful source comparison can be made.')

def research(q, category):
 jobs = []
 if category in ('all', 'business'): jobs.append(('SEC EDGAR', sec_search, q))
 if category in ('all', 'genealogy'): jobs.append(('Library of Congress', loc_search, q))
 if category in ('all', 'court'): jobs.append(('CourtListener', court_search, q))
 items, statuses = [], []
 with ThreadPoolExecutor(max_workers=3) as pool:
  for results, status in pool.map(lambda args: connector(*args), jobs):
   items.extend(results); statuses.append(status)
 return items, statuses

def validated(q, category):
 return isinstance(q, str) and 2 <= len(q.strip()) <= 120 and isinstance(category, str) and category in CATEGORIES

@app.get('/health')
def health():
 return jsonify(status='ok', service='public-records-research', version=VERSION)

@app.get('/api/sources')
def sources():
 return jsonify([dict(name=n, description=d, category=c, url=u.replace('{q}', '')) for n, d, u, c in SOURCES])

@app.get('/api/search')
def search():
 q = request.args.get('q', '').strip(); category = request.args.get('category', 'all')
 if not validated(q, category): return jsonify(error='Enter 2–120 characters and a valid category.'), 400
 items, statuses = research(q, category)
 links = [dict(title=n, description=d, category=c, url=u.replace('{q}', quote_plus(q)), status='source_link', verified_record=False) for n, d, u, c in SOURCES if category in ('all', c)]
 return jsonify(query=q, results=items + links, sources=statuses, warnings=[s['message'] for s in statuses if s['message']],
                searched_at=now(), notice='Retrieved records are source-attributed search results, not independently verified facts. Portal links are not record matches.')

@app.post('/api/watches/check')
def check():
 data = request.get_json(silent=True)
 if not isinstance(data, dict): return jsonify(error='JSON object required.'), 400
 q=data.get('query', ''); category=data.get('category', 'all'); previous=data.get('previous', {})
 if not validated(q, category) or not isinstance(previous, dict): return jsonify(error='Invalid watch.'), 400
 for source, rows in previous.items():
  if source not in ('SEC EDGAR', 'Library of Congress', 'CourtListener') or not isinstance(rows, list) or len(rows)>50 or any(not isinstance(r,dict) or not all(isinstance(r.get(k),str) for k in ('url','title','description')) for r in rows):
   return jsonify(error='Invalid snapshot.'), 400
 items, statuses = research(q.strip(), category)
 snapshots = dict(previous); comparisons=[]
 for status in statuses:
  source = status['source']
  if status['status'] != 'ok':
   comparisons.append(dict(source=source, status=status['status'], message=status['message'])); continue
  current = [dict(url=r['url'], title=r['title'], description=r['description']) for r in items if r['source'] == source]
  snapshots[source] = current
  if source not in previous:
   comparisons.append(dict(source=source, status='baseline', count=len(current))); continue
  before={r['url']:r for r in previous[source]}; after={r['url']:r for r in current}
  comparisons.append(dict(source=source, status='compared', added=[after[u] for u in sorted(after.keys()-before.keys())],
                          removed=[before[u] for u in sorted(before.keys()-after.keys())],
                          updated=[after[u] for u in sorted(before.keys()&after.keys()) if before[u] != after[u]]))
 return jsonify(checked_at=now(), snapshots=snapshots, comparisons=comparisons,
                notice='Compares a limited result window, not every underlying record. Checks run on demand or every 15 minutes while this page is open.')

@app.route('/api/watches', methods=['GET', 'POST'])
def old_watches():
 return jsonify(error='Watches are now private to this browser. Shared storage has been retired.'), 410

@app.after_request
def headers(response):
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['Referrer-Policy']='no-referrer'
 response.headers['Cache-Control']='no-store'
 return response

PAGE="""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RecordScope | Public Records Research</title><style>
:root{font-family:Inter,system-ui,Arial;background:#0b1424;color:#f1f5fa}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1000px;margin:auto;padding:32px 18px}header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #273449;padding-bottom:22px}.brand{font-size:25px;font-weight:800;letter-spacing:-.6px}.brand b{color:#58caa6}.muted{color:#a9b8cb}h1{font-size:clamp(32px,5vw,52px);margin:55px 0 12px;line-height:1.08}p{line-height:1.6}.panel,.result{background:#15243a;border:1px solid #2d4058;border-radius:14px;padding:22px;margin-top:18px}input,select,button{padding:13px 15px;border-radius:9px;font:inherit}input,select{background:#0b1424;border:1px solid #465a73;color:white}input{flex:1;min-width:160px}button{background:#50c79e;color:#061b17;border:0;font-weight:800;cursor:pointer}.controls{display:flex;gap:10px;flex-wrap:wrap}.result a{color:#75d9b7;font-weight:700}.tag{display:inline-block;background:#29415a;border-radius:6px;padding:4px 8px;font-size:12px;margin-bottom:8px}.small{font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}footer{margin-top:55px;border-top:1px solid #273449;padding-top:20px}
</style></head><body><div class="wrap"><header><div class="brand">RECORD<b>SCOPE</b></div><span class="muted small">Public-source intelligence · MVP</span></header><h1>Research records.<br><span style="color:#58caa6">Verify the source.</span></h1><p class="muted">Nationwide court resources, business filings, and historical genealogy. Source-first results, never invented matches.</p><div class="panel"><div class="controls"><input id="q" placeholder="Company, case number, or historical research term" aria-label="Search query"><select id="cat"><option value="all">All sources</option><option value="court">Courts</option><option value="business">Businesses</option><option value="genealogy">Genealogy</option></select><button onclick="search()">Search records</button><button onclick="watch()" style="background:#354c64;color:white">Save watch</button></div><p class="muted small">Links lead to official or established research portals. Results are not identity verification. Avoid using this service to locate or track private individuals.</p></div><p id="searchnotice" class="muted small" role="status"></p><h2>Research results</h2><div id="results" class="grid"><div class="result muted">Enter a research term to begin.</div></div><h2>Saved watches</h2><div class="panel"><button onclick="check()">Check watch status</button><p id="watchnotice" class="muted small">Watches stay in this browser. Checks compare retrieved records every 15 minutes while this page is open. Court checks require a connected API token.</p><div id="watches"></div></div><footer class="muted small">RecordScope · No scraping behind logins, bypassing CAPTCHAs, or claiming incomplete records are comprehensive. Limited source coverage. No comprehensive nationwide record or identity verification. Watches are saved on this device.</footer></div><script>
const el=id=>document.getElementById(id);
function safe(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let watches=[];try{watches=JSON.parse(localStorage.getItem('recordscope-watches-v2')||'[]');if(!Array.isArray(watches))watches=[]}catch(e){}
let checking=false;
function persist(){try{localStorage.setItem('recordscope-watches-v2',JSON.stringify(watches))}catch(e){el('watchnotice').textContent='Device storage unavailable. Watches will be lost when this page closes.'}}
async function api(url,options){const r=await fetch(url,options);const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
async function search(){const q=el('q').value.trim();if(q.length<2)return alert('Enter at least two characters');el('results').textContent='Loading...';try{let d=await api('/api/search?q='+encodeURIComponent(q)+'&category='+encodeURIComponent(el('cat').value));el('searchnotice').textContent=d.notice+' '+d.warnings.join(' ');el('results').innerHTML=d.results.map(x=>'<div class="result"><span class="tag">'+safe(x.category)+' · '+(x.status==='api_result'?'Retrieved record':'Research portal')+'</span><h3>'+safe(x.title)+'</h3><p class="muted">'+safe(x.description)+'</p><a target="_blank" rel="noopener noreferrer" href="'+safe(x.url)+'">Open source ↗</a></div>').join('');}catch(e){el('results').textContent=e.message}}
async function watch(){let query=el('q').value.trim(),category=el('cat').value;if(query.length<2)return alert('Enter a search first');if(watches.some(w=>w.query===query&&w.category===category))return alert('Already saved');if(watches.length>=10)return alert('Maximum 10 watches per device');watches.push({query,category,previous:{},last_checked:null,summary:'Ready for first check'});persist();load();await check()}
function load(){el('watches').innerHTML=watches.map((w,i)=>'<div class="result"><b>'+safe(w.query)+'</b> · '+safe(w.category)+'<p class="small muted">'+safe(w.summary)+' · Checked: '+safe(w.last_checked||'never')+'</p><button onclick="removeWatch('+i+')">Remove</button></div>').join('')||'<p class="muted">No watches saved on this device.</p>'}
function removeWatch(i){if(checking)return;watches.splice(i,1);persist();load()}
async function check(){if(checking)return;checking=true;el('watchnotice').textContent='Checking connected sources...';try{for(let w of watches){try{let d=await api('/api/watches/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:w.query,category:w.category,previous:w.previous})});w.previous=d.snapshots;w.last_checked=d.checked_at;w.summary=d.comparisons.map(c=>c.source+': '+(c.status==='compared'?c.added.length+' added, '+c.removed.length+' left result window, '+c.updated.length+' updated':c.status==='baseline'?'baseline saved ('+c.count+' records)':c.message)).join(' | ')}catch(e){w.summary='Check failed: '+e.message}persist();load()}el('watchnotice').textContent='Checks compare limited result windows. Automatic checks run every 15 minutes while this page is open. Source failures preserve the previous snapshot.'}finally{checking=false}}
el('q').addEventListener('keydown',e=>{if(e.key==='Enter')search()});setInterval(()=>{if(watches.length)check()},900000);load();
</script></body></html>"""
@app.get("/")
def home(): return render_template_string(PAGE)
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
