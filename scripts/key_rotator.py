import json,os,time,requests
class OpenRouterKeyRotator:
 def __init__(self,secret="OPENROUTER_KEYS_JSON",retries=5,timeout=90):
  try:self.keys=[str(x).strip() for x in json.loads(os.getenv(secret,"[]")) if str(x).strip()]
  except Exception as e:raise RuntimeError(f"{secret} must be a JSON array") from e
  if not self.keys:raise RuntimeError("No OpenRouter API keys configured")
  self.i=0;self.retries=retries;self.timeout=timeout
 @property
 def key(self):return self.keys[self.i%len(self.keys)]
 def rotate(self):self.i=(self.i+1)%len(self.keys)
 def request(self,method,url,**kw):
  last=None
  for n in range(self.retries):
   h=dict(kw.pop("headers",{}) or {});h["Authorization"]="Bearer "+self.key;h.setdefault("Content-Type","application/json")
   try:r=requests.request(method,url,headers=h,timeout=self.timeout,**kw)
   except requests.RequestException as e:last=e;self.rotate();time.sleep(min(2**n,10));continue
   if r.status_code not in (402,429):return r
   last=RuntimeError(f"OpenRouter HTTP {r.status_code}");self.rotate();time.sleep(min(2**n,10))
  raise last or RuntimeError("OpenRouter request failed")
 def chat(self,payload):return self.request("POST","https://openrouter.ai/api/v1/chat/completions",json=payload)