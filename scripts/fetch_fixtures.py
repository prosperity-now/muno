import argparse,json,re,sys,time
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"data/matches.json"
S=requests.Session(); S.headers["User-Agent"]="MUNO-Soccer-Analytics/1.0"
def search(q):
 r=S.get("https://html.duckduckgo.com/html/?q="+quote_plus(q),timeout=25); r.raise_for_status()
 return [(a.get_text(" ",strip=True),a.get("href","")) for a in BeautifulSoup(r.text,"html.parser").select(".result__a")[:10]]
def collect(date):
 found=[]
 for q in [f"football fixtures {date}",f"soccer fixtures {date}"]:
  try: results=search(q)
  except requests.RequestException as e: print(e,file=sys.stderr); continue
  for title,url in results:
   if date not in title+" "+url: continue
   try:
    r=S.get(url,timeout=20); r.raise_for_status()
    text=" ".join(BeautifulSoup(r.text,"html.parser").stripped_strings)
   except requests.RequestException: continue
   for pat in [r"([A-Z][A-Za-z0-9 .&'’_-]{2,40})\s+(?:vs\.?|v)\s+([A-Z][A-Za-z0-9 .&'’_-]{2,40})",r"([A-Z][A-Za-z0-9 .&'’_-]{2,40})\s+[-–]\s+([A-Z][A-Za-z0-9 .&'’_-]{2,40})"]:
    m=re.search(pat,text)
    if m: found.append((m.group(1).strip(),m.group(2).strip(),url)); break
  if found: break
  time.sleep(.5)
 out=[]; seen=set()
 for h,a,url in found:
  k=(h.lower(),a.lower(),date)
  if k in seen: continue
  seen.add(k); mid=re.sub(r"[^a-z0-9]+","-",f"{date}-{h}-{a}".lower()).strip("-")
  out.append({"match_id":mid,"id":mid,"date":date,"competition":"Football","kickoff":"TBD","home_team":{"name":h},"away_team":{"name":a},"source":url})
 return out
def main():
 p=argparse.ArgumentParser(); p.add_argument("--date",required=True); a=p.parse_args()
 datetime.strptime(a.date,"%Y-%m-%d"); new=collect(a.date); old=[]
 if OUT.exists():
  try: old=json.loads(OUT.read_text())
  except: old=[]
 if isinstance(old,dict): old=old.get("matches",[])
 merged=[x for x in old if x.get("date")!=a.date]+new
 merged.sort(key=lambda x:(x.get("date",""),x.get("kickoff",""),x.get("match_id","")))
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+"\n")
 print("Fetched",len(new),"fixtures for",a.date)
if __name__=="__main__": main()
