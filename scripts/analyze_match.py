import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from key_rotator import OpenRouterKeyRotator
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"data/analyses"
S=requests.Session(); S.headers["User-Agent"]="MUNO-Soccer-Analytics/1.0"
def search(q):
 try:
  r=S.get("https://html.duckduckgo.com/html/",params={"q":q},timeout=25); r.raise_for_status()
  return [(a.get_text(" ",strip=True),a.get("href","")) for a in BeautifulSoup(r.text,"html.parser").select(".result__a")[:6]]
 except requests.RequestException:return []
def text(url):
 try:
  r=S.get(url,timeout=20); r.raise_for_status(); return BeautifulSoup(r.text,"html.parser").get_text(" ",strip=True)[:6000]
 except requests.RequestException:return ""
def research(h,a):
 rows=[]
 for q in [f"{h} recent results FBref",f"{a} recent results FBref",f"{h} {a} H2H SofaScore",f"{h} injuries Transfermarkt",f"{a} injuries Transfermarkt",f"{h} {a} lineup"]:
  for title,url in search(q)[:3]: rows.append({"query":q,"title":title,"url":url,"text":text(url)})
 return rows
def fallback(rows):
 t=" ".join(x["text"].lower() for x in rows); w=1+.03*t.count("win"); d=1+.02*t.count("draw"); l=1+.02*t.count("loss"); z=w+d+l
 return {"home_win":w/z,"draw":d/z,"away_win":l/z}
def llm(rot,prompt):
 r=rot.chat({"model":"google/gemini-2.5-flash","messages":[{"role":"system","content":"You are a soccer analytics engine. Return strict JSON and never invent unavailable facts."},{"role":"user","content":prompt}]})
 if not r.ok: raise RuntimeError(r.text[:500])
 return json.loads(r.json()["choices"][0]["message"]["content"])
def main():
 p=argparse.ArgumentParser(); p.add_argument("--match-id",required=True); p.add_argument("--home",required=True); p.add_argument("--away",required=True); a=p.parse_args()
 rows=research(a.home,a.away); fb=fallback(rows); result=None
 prompt=f"""Analyze {a.home} vs {a.away} using only this research. Return JSON keys probabilities (home_win,draw,away_win), home (name,recent_form), away (name,recent_form), h2h_summary, injury_summary, key_stats, tactical_rationale, sources. Normalize probabilities to sum to 1. Do not invent facts; use unavailable where evidence is absent. Research: {json.dumps(rows,ensure_ascii=False)[:30000]}"""
 try: result=llm(OpenRouterKeyRotator(),prompt)
 except Exception as e: print("LLM unavailable:",e)
 if not isinstance(result,dict): result={"probabilities":fb,"home":{"name":a.home,"recent_form":[]},"away":{"name":a.away,"recent_form":[]},"h2h_summary":"Unavailable","injury_summary":"Unavailable","key_stats":{},"tactical_rationale":"Insufficient evidence for synthesis.","sources":[x["url"] for x in rows]}
 p=result.get("probabilities",fb); v=[max(0,float(p.get("home_win",fb["home_win"]))),max(0,float(p.get("draw",fb["draw"]))),max(0,float(p.get("away_win",fb["away_win"])))]
 z=sum(v) or 1; result["probabilities"]={"home_win":v[0]/z,"draw":v[1]/z,"away_win":v[2]/z}
 result.update({"match_id":a.match_id,"home_team":a.home,"away_team":a.away,"generated_at":datetime.now(timezone.utc).isoformat(),"model":"google/gemini-2.5-flash via OpenRouter"})
 OUT.mkdir(parents=True,exist_ok=True); (OUT/f"{a.match_id}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__": main()
