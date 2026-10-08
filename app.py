import os, sqlite3, time, hashlib, json
from urllib.parse import quote_plus
from flask import Flask, request, jsonify, render_template_string
import requests

app=Flask(__name__)
DB=os.getenv("DATABASE_PATH","/tmp/records_mvp.sqlite3")
SOURCES=[
 ("CourtListener","Court opinions and available dockets","https://www.courtlistener.com/?q={q}","court"),
 ("PACER","Federal court docket access (may require fees)","https://pacer.uscourts.gov/","court"),
 ("SEC EDGAR","Company filings","https://www.sec.gov/edgar/search/#/q={q}","business"),
 ("USAspending","Federal spending and award data","https://www.usaspending.gov/search","business"),
 ("National Archives","Historical government records","https://catalog.archives.gov/search?q={q}","genealogy"),
 ("FamilySearch","Genealogy; account may be required","https://www.familysearch.org/search/","genealogy"),
 ("NARA Census","Historical census research","https://www.archives.gov/research/census","genealogy"),
 ("State court directory","State-by-state court resources","https://www.ncsc.org/information-and-resources/state-court-websites","court"),
 ("State business registries","Secretary of State directory","https://www.nass.org/business-services/corporate-registration","business"),
]
def db():
 c=sqlite3.connect(DB,timeout=10)
 c.execute("CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY, category TEXT NOT NULL, query TEXT NOT NULL, fingerprint TEXT, checked_at TEXT)")
 c.commit()
 return c
@app.get("/health")
def health(): return jsonify(status="ok",service="public-records-research")
@app.get("/api/sources")
def sources(): return jsonify([dict(name=n,description=d,category=c) for n,d,u,c in SOURCES])
@app.get("/api/search")
def search():
 q=request.args.get("q","").strip()[:120]
 category=request.args.get("category","all")
 if not q or len(q)<2: return jsonify(error="Enter at least 2 characters"),400
 if category not in ("all","court","business","genealogy"): return jsonify(error="Invalid category"),400
 items=[dict(title=n,description=d,category=c,url=u.replace("{q}",quote_plus(q)),status="source_link",verified_record=False) for n,d,u,c in SOURCES if category in ("all",c)]
 # Optional live search of CourtListener API; never imply a link-only result was searched.
 if category in ("all","court") and os.getenv("COURTLISTENER_API_TOKEN"):
  try:
   response=requests.get("https://www.courtlistener.com/api/rest/v3/search/",params={"q":q,"type":"o"},headers={"Authorization":"Token "+os.environ["COURTLISTENER_API_TOKEN"]},timeout=8)
   if response.ok:
    data=response.json()
    for r in data.get("results",[])[:8]:
     path=r.get("absolute_url") or ""
     if not path.startswith("/"): continue
     items.insert(0,dict(title=str(r.get("caseName") or "Court opinion")[:180],description=str(r.get("court") or "CourtListener")[:120],category="court",url="https://www.courtlistener.com"+path,status="api_result",verified_record=True))
  except (requests.RequestException,ValueError): pass
 return jsonify(query=q,results=items,notice="Source links are not verified record matches. API results are labeled separately. Confirm identity and details at the original source.",searched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
@app.route("/api/watches",methods=["GET","POST"])
def watches():
 c=db()
 if request.method=="POST":
  data=request.get_json(silent=True) or {}
  q=str(data.get("query","")).strip()[:120];cat=data.get("category","all")
  if len(q)<2 or cat not in ("all","court","business","genealogy"): return jsonify(error="Invalid watch"),400
  c.execute("INSERT INTO watches(category,query) VALUES (?,?)",(cat,q));c.commit()
 rows=c.execute("SELECT id,category,query,checked_at FROM watches ORDER BY id DESC LIMIT 100").fetchall()
 c.close()
 return jsonify([dict(id=i,category=cat,query=q,last_checked=checked) for i,cat,q,checked in rows])
@app.post("/api/watches/check")
def check():
 # Checks the saved query catalog, not remote sources; avoids false change alerts.
 c=db();now=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
 c.execute("UPDATE watches SET checked_at=?",(now,));c.commit()
 count=c.execute("SELECT COUNT(*) FROM watches").fetchone()[0];c.close()
 return jsonify(checked=count,at=now,changes_detected=None,notice="Remote change detection requires approved source-specific integrations. No changes are claimed.")
PAGE="""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RecordScope | Public Records Research</title><style>
:root{font-family:Inter,system-ui,Arial;background:#0b1424;color:#f1f5fa}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1000px;margin:auto;padding:32px 18px}header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #273449;padding-bottom:22px}.brand{font-size:25px;font-weight:800;letter-spacing:-.6px}.brand b{color:#58caa6}.muted{color:#a9b8cb}h1{font-size:clamp(32px,5vw,52px);margin:55px 0 12px;line-height:1.08}p{line-height:1.6}.panel,.result{background:#15243a;border:1px solid #2d4058;border-radius:14px;padding:22px;margin-top:18px}input,select,button{padding:13px 15px;border-radius:9px;font:inherit}input,select{background:#0b1424;border:1px solid #465a73;color:white}input{flex:1;min-width:160px}button{background:#50c79e;color:#061b17;border:0;font-weight:800;cursor:pointer}.controls{display:flex;gap:10px;flex-wrap:wrap}.result a{color:#75d9b7;font-weight:700}.tag{display:inline-block;background:#29415a;border-radius:6px;padding:4px 8px;font-size:12px;margin-bottom:8px}.small{font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}footer{margin-top:55px;border-top:1px solid #273449;padding-top:20px}
</style></head><body><div class="wrap"><header><div class="brand">RECORD<b>SCOPE</b></div><span class="muted small">Public-source intelligence · MVP</span></header><h1>Research records.<br><span style="color:#58caa6">Verify the source.</span></h1><p class="muted">Nationwide court resources, business filings, and historical genealogy. Source-first results, never invented matches.</p><div class="panel"><div class="controls"><input id="q" placeholder="Company, case number, or historical research term" aria-label="Search query"><select id="cat"><option value="all">All sources</option><option value="court">Courts</option><option value="business">Businesses</option><option value="genealogy">Genealogy</option></select><button onclick="search()">Find sources</button><button onclick="watch()" style="background:#354c64;color:white">Save watch</button></div><p class="muted small">Links lead to official or established research portals. Results are not identity verification. Avoid using this service to locate or track private individuals.</p></div><h2>Research results</h2><div id="results" class="grid"><div class="result muted">Enter a research term to begin.</div></div><h2>Saved watches</h2><div class="panel"><button onclick="check()">Check watch status</button><p id="watchnotice" class="muted small">Automated remote record-change monitoring requires authorized integrations.</p><div id="watches"></div></div><footer class="muted small">RecordScope · No scraping behind logins, bypassing CAPTCHAs, or claiming incomplete records are comprehensive. Free Render storage may be ephemeral.</footer></div><script>
const el=id=>document.getElementById(id);
function safe(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function search(){const q=el('q').value.trim();if(q.length<2)return alert('Enter at least two characters');el('results').textContent='Loading...';try{let r=await fetch('/api/search?q='+encodeURIComponent(q)+'&category='+encodeURIComponent(el('cat').value));let d=await r.json();el('results').innerHTML=d.results.map(x=>'<div class="result"><span class="tag">'+safe(x.category)+' · '+safe(x.status)+'</span><h3>'+safe(x.title)+'</h3><p class="muted">'+safe(x.description)+'</p><a target="_blank" rel="noopener noreferrer" href="'+safe(x.url)+'">Open source ↗</a></div>').join('');}catch(e){el('results').textContent='Search unavailable. Try again.'}}
async function watch(){let q=el('q').value.trim();if(q.length<2)return alert('Enter a search first');await fetch('/api/watches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,category:el('cat').value})});load()}
async function load(){let r=await fetch('/api/watches');let d=await r.json();el('watches').innerHTML=d.map(x=>'<p>'+safe(x.query)+' <span class="muted small">('+safe(x.category)+', last checked: '+safe(x.last_checked||'never')+')</span></p>').join('')||'<p class="muted">No saved watches yet.</p>'}
async function check(){let r=await fetch('/api/watches/check',{method:'POST'});let d=await r.json();el('watchnotice').textContent=d.notice;load()}load()
</script></body></html>"""
@app.get("/")
def home(): return render_template_string(PAGE)
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
