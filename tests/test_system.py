import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as module


def test_search_labels_and_validation(monkeypatch):
 monkeypatch.setattr(module, 'research', lambda q,c: ([module.record('Item','Text','https://www.loc.gov/item/1/','genealogy','Library of Congress')], []))
 client=module.app.test_client()
 assert client.get('/api/search?q=x').status_code==400
 assert client.get('/api/search?q=Virginia&category=invalid').status_code==400
 results=client.get('/api/search?q=Virginia&category=genealogy').json['results']
 assert results[0]['status']=='api_result' and results[0]['verified_record'] is False
 assert any(r['status']=='source_link' for r in results)
 assert client.get('/api/watches').status_code==410


def test_monitor_baseline_changes_and_outage(monkeypatch):
 item=module.record('One','Original','https://www.loc.gov/item/1/','genealogy','Library of Congress')
 status=dict(source='Library of Congress',status='ok',count=1,message=None)
 monkeypatch.setattr(module,'research',lambda q,c: ([item],[status]))
 client=module.app.test_client();body={'query':'Virginia','category':'genealogy','previous':{}}
 baseline=client.post('/api/watches/check',json=body).json
 assert baseline['comparisons'][0]['status']=='baseline'
 body['previous']=baseline['snapshots']
 unchanged=client.post('/api/watches/check',json=body).json
 assert unchanged['comparisons'][0]['added']==[]
 item['description']='Changed'
 changed=client.post('/api/watches/check',json=body).json
 assert changed['comparisons'][0]['updated'][0]['description']=='Changed'
 added=module.record('Two','New','https://www.loc.gov/item/2/','genealogy','Library of Congress')
 monkeypatch.setattr(module,'research',lambda q,c: ([added],[status]))
 result=client.post('/api/watches/check',json=body).json['comparisons'][0]
 assert len(result['added'])==1 and len(result['removed'])==1
 monkeypatch.setattr(module,'research',lambda q,c: ([],[dict(source='Library of Congress',status='unavailable',message='Unavailable')]))
 failed=client.post('/api/watches/check',json=body).json
 assert failed['snapshots']==body['previous']
 assert failed['comparisons'][0]['status']=='unavailable'


def test_bad_snapshot_and_missing_token(monkeypatch):
 client=module.app.test_client()
 assert client.post('/api/watches/check',json={'query':'VA','previous':{'anything':[]}}).status_code==400
 assert client.post('/api/watches/check',json=[]).status_code==400
 monkeypatch.delenv('COURTLISTENER_API_TOKEN',raising=False)
 monkeypatch.delenv('SEC_USER_AGENT',raising=False)
 assert module.court_search('copyright')[1]=='not_configured'
 assert module.sec_search('Apple')[1]=='not_configured'
 assert not module.allowed_url('https://loc.gov.evil.example/item/1','loc.gov')


def test_sec_filings_and_loc_provenance(monkeypatch):
 monkeypatch.setenv('SEC_USER_AGENT','Test Suite example@example.org')
 def fake(url,params=None,headers=None):
  if 'submissions' in url:
   return {'name':'Example Inc','filings':{'recent':{'accessionNumber':['0000320193-26-000001'],'primaryDocument':['report.htm'],'form':['10-K'],'filingDate':['2026-01-01']}}}
  return {'results':[{'title':'Virginia map','url':'https://www.loc.gov/item/123/','description':['Historical map'],'date':'1900'}, {'title':'Unsafe','url':'javascript:alert(1)'}]}
 monkeypatch.setattr(module,'get_json',fake)
 filings=module.sec_search('CIK 320193')
 assert filings[1]['url']=='https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/report.htm'
 assert filings[1]['source']=='SEC EDGAR'
 assert len(module.loc_search('Virginia'))==1
