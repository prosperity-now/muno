import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from browser_use import Agent, ChatOpenRouter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"browser_fixtures.json"
TASK="""You are the MUNO fixture-collection browser agent.

Use a real browser with Browser Use and collect soccer fixtures for {date}.
Do NOT use direct HTTP/API requests. Navigate rendered websites and inspect their pages.

Start with SofaScore's football matches area. Set the date to {date}. If it fails or does not expose the date cleanly, use Flashscore football as the fallback, then ESPN's rendered website as a second fallback.

Collect professional men's football scheduled for that date, prioritizing major domestic leagues and UEFA competitions. Do not invent fixtures or infer them from search snippets.

Return ONLY valid JSON:
{{
  "date": "{date}",
  "source": "website actually inspected",
  "fixtures": [
    {{
      "match_id": "stable-short-id",
      "date": "{date}",
      "competition": "competition name",
      "kickoff": "ISO timestamp if visible, otherwise visible time or TBD",
      "home_team": {{"name": "Home team"}},
      "away_team": {{"name": "Away team"}},
      "venue": "venue if visible, otherwise empty string",
      "source": "page URL actually inspected"
    }}
  ]
}}
Rules: only include fixtures verified on rendered pages; deduplicate; preserve home/away order; scroll when needed; if a site fails, actually navigate to the fallback; no prose outside JSON."""

def clean_json(v):
    v=(v or "").strip()
    v=re.sub(r"^\x60\x60\x60(?:json)?\s*","",v,flags=re.I)
    v=re.sub(r"\s*\x60\x60\x60$","",v)
    a,b=v.find("{"),v.rfind("}")
    if a<0 or b<a: raise ValueError("Browser agent did not return JSON")
    return json.loads(v[a:b+1])

async def run_agent(date):
    raw=os.environ.get("OPENROUTER_KEYS_JSON","")
    try: keys=json.loads(raw)
    except json.JSONDecodeError as e: raise RuntimeError("OPENROUTER_KEYS_JSON must be a JSON array") from e
    if not isinstance(keys,list) or not keys: raise RuntimeError("OPENROUTER_KEYS_JSON has no keys")
    last=None
    for i,key in enumerate(keys,1):
        try:
            llm=ChatOpenRouter(model="google/gemini-2.5-flash", api_key=key)
            agent=Agent(task=TASK.format(date=date),llm=llm,max_steps=80)
            history=await agent.run()
            result=clean_json(history.final_result())
            result["agent"]="browser-use"; result["agent_attempt"]=i
            return result
        except Exception as e:
            last=e; print(f"Browser agent attempt {i} failed: {e}")
    raise RuntimeError(f"All browser-agent attempts failed: {last}")

def normalize(payload,date):
    fixtures=payload.get("fixtures") if isinstance(payload,dict) else None
    if not isinstance(fixtures,list): raise ValueError("Browser agent returned no fixtures array")
    clean=[]; seen=set()
    for item in fixtures:
        if not isinstance(item,dict): continue
        h=item.get("home_team",{}); a=item.get("away_team",{})
        h=h.get("name") if isinstance(h,dict) else h; a=a.get("name") if isinstance(a,dict) else a
        if not h or not a: continue
        key=(date,str(h).strip().lower(),str(a).strip().lower())
        if key in seen: continue
        seen.add(key)
        raw=str(item.get("match_id") or "").strip()
        mid=re.sub(r"[^a-z0-9]+","-",raw.lower()).strip("-") or re.sub(r"[^a-z0-9]+","-",f"{date}-{h}-{a}".lower()).strip("-")
        clean.append({"match_id":mid,"id":mid,"date":date,"competition":str(item.get("competition") or "Football"),"kickoff":item.get("kickoff") or "TBD","venue":item.get("venue") or "","home_team":{"name":str(h).strip()},"away_team":{"name":str(a).strip()},"source":item.get("source") or payload.get("source") or "","source_provider":"browser-use"})
    if not clean: raise ValueError(f"Browser agent found no verified fixtures for {date}")
    return clean

async def main():
    p=argparse.ArgumentParser(); p.add_argument("--date",required=True); args=p.parse_args(); datetime.strptime(args.date,"%Y-%m-%d")
    fixtures=normalize(await run_agent(args.date),args.date)
    old=[]
    if OUT.exists():
        try: old=json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError): old=[]
    if isinstance(old,dict): old=old.get("fixtures",[])
    merged=[x for x in old if x.get("date")!=args.date]+fixtures
    merged.sort(key=lambda x:(x.get("date",""),x.get("kickoff",""),x.get("competition",""),x.get("match_id","")))
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    path=ROOT/"data"/"matches.json"; existing=[]
    if path.exists():
        try: existing=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError): existing=[]
    if isinstance(existing,dict): existing=existing.get("matches",[])
    existing=[x for x in existing if x.get("date")!=args.date]+fixtures
    existing.sort(key=lambda x:(x.get("date",""),x.get("kickoff",""),x.get("match_id","")))
    path.write_text(json.dumps(existing,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Browser Use collected {len(fixtures)} verified fixtures for {args.date}")

if __name__=="__main__": asyncio.run(main())
