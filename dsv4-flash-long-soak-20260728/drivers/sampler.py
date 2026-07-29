#!/usr/bin/env python3
"""Independent memory/health sampler. Records FAILURES explicitly -- a missing
sample must never be indistinguishable from a healthy one."""
import json, subprocess, time, os, urllib.request
OUT=os.path.expanduser("~/staging/dsv4-long-soak-20260728/raw/sampler.jsonl")
NODES=["node-a","node-b"]
def iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
while True:
    rec={"ts":iso(),"nodes":{}}
    for n in NODES:
        try:
            p=subprocess.run(["ssh","-n","-o","ConnectTimeout=10","-o","BatchMode=yes",n,
                "free -m | awk '/Mem:/{print \"m\",$2,$3,$7} /Swap:/{print \"s\",$3}'; "
                "uptime | sed 's/.*load average: //'; "
                "docker inspect dsv4_ablit_mida --format '{{.State.Status}} {{.RestartCount}}'"],
                capture_output=True,text=True,timeout=30)
            if p.returncode!=0:
                rec["nodes"][n]={"sample_ok":False,"reason":"ssh_rc","rc":p.returncode,
                                 "stderr":p.stderr[:200]}
                continue
            d={"sample_ok":True,"raw":p.stdout.strip()[:400]}
            for line in p.stdout.splitlines():
                f=line.split()
                if f and f[0]=="m" and len(f)>=4:
                    d["total_mb"],d["used_mb"],d["avail_mb"]=int(f[1]),int(f[2]),int(f[3])
                elif f and f[0]=="s" and len(f)>=2:
                    d["swap_used_mb"]=int(f[1])
                elif "running" in line or "exited" in line:
                    d["container_status"]=line.split()[0]
                    d["restart_count"]=int(line.split()[1])
            if "avail_mb" not in d:
                d["sample_ok"]=False; d["reason"]="parse_incomplete"
            rec["nodes"][n]=d
        except Exception as e:
            rec["nodes"][n]={"sample_ok":False,"reason":type(e).__name__,"err":repr(e)[:200]}
    try:
        b=urllib.request.urlopen("http://REDACTED_IPHOST:PORT/health",timeout=15)
        rec["health_http"]=b.status
    except Exception as e:
        rec["health_http"]=0; rec["health_err"]=repr(e)[:150]
    with open(OUT,"a") as fh: fh.write(json.dumps(rec)+"\n")
    time.sleep(120)
