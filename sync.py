#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sincronização automática Garmin -> plataforma de estímulos.
Corre todos os dias (GitHub Actions). Faz login na tua conta Garmin,
vai buscar as atividades novas desde a última sincronização, descarrega
o ficheiro FIT de cada corrida, reconstrói as séries (repetição a
repetição) e atualiza os dados do site.

Não precisas de mexer aqui. As credenciais vêm de duas "secrets" do
GitHub: GARMIN_EMAIL e GARMIN_PASSWORD.
"""
import os, io, json, zipfile, datetime, statistics, traceback
from collections import Counter
from garminconnect import Garmin
from garmin_fit_sdk import Stream, Decoder

DATA = "data"
NICE = [100,150,200,300,400,500,600,800,1000,1200,1500,2000,3000,5000]
RUNMAP = {"running":"estrada","street_running":"estrada","trail_running":"trail",
          "treadmill_running":"passadeira","indoor_running":"passadeira",
          "track_running":"pista"}

# ---------- reconstrução de intervalos (idêntica ao motor validado) ----------
def snap(d):
    if not d: return None
    return min(NICE, key=lambda x: abs(x-d))

def seasonOf(y,m,d):
    if m>=9 or (m==8 and d>=25): return f"{y}/{y+1}"
    return f"{y-1}/{y}"

def cad(l):
    c = l.get("avg_running_cadence")
    if c is None: c = l.get("avg_cadence")
    if c is None: return None
    return round((c + (l.get("avg_fractional_cadence") or 0)) * 2)

def keyOf(w):
    return f"{w['date']}#{w['type']}#{w.get('rep_distance_m') or ''}#{w.get('n_reps') or ''}"

def reconstruct(fit_bytes):
    """Recebe os bytes de um FIT e devolve uma sessão de séries, ou None."""
    try:
        msgs, _ = Decoder(Stream.from_byte_array(bytearray(fit_bytes))).read()
    except Exception:
        return None
    sess = msgs.get("session_mesgs") or []
    if not sess: return None
    s = sess[0]
    if s.get("sport") != "running": return None
    laps = msgs.get("lap_mesgs", [])
    if len(laps) < 3: return None
    recs = msgs.get("record_mesgs", [])
    start = s.get("start_time")
    if not start: return None
    y, mo, da = start.year, start.month, start.day
    series = [(r.get("timestamp"), r.get("heart_rate")) for r in recs
              if r.get("timestamp") and r.get("heart_rate") is not None]
    series.sort(key=lambda x: x[0])
    def hr_near(ts):
        if not ts or not series: return None
        best=None; bd=1e9
        for t,h in series:
            dd=abs((t-ts).total_seconds())
            if dd<bd: bd=dd; best=h
        return best if bd<15 else None
    L=[]
    for l in laps:
        L.append(dict(
            d=round(l.get("total_distance") or 0),
            t=round((l.get("total_timer_time") or l.get("total_elapsed_time") or 0),1),
            hr=l.get("avg_heart_rate"), hrmax=l.get("max_heart_rate"), cad=cad(l),
            step=round(l.get("avg_step_length")) if l.get("avg_step_length") else None,
            gct=round(l.get("avg_stance_time")) if l.get("avg_stance_time") else None,
            vo=round(l.get("avg_vertical_oscillation"),1) if l.get("avg_vertical_oscillation") else None,
            start=l.get("start_time")))
    counts=Counter(snap(x["d"]) for x in L if x["d"] and snap(x["d"]))
    if not counts: return None
    top=[k for k,_ in counts.most_common(2)]
    workDist=max(top)
    isW=lambda x: snap(x["d"])==workDist and x["d"]>=100
    works0=[x for x in L if isW(x)]
    if len(works0)<2: return None
    med=statistics.median([w["t"] for w in works0])
    keep=set(id(w) for w in works0 if 0.5*med <= w["t"] <= 1.7*med)
    works=[x for x in L if id(x) in keep]
    if len(works)<2: return None
    wset=set(id(w) for w in works)
    wIdx=[i for i,x in enumerate(L) if id(x) in wset]
    recovs=[]
    for k in range(len(wIdx)-1):
        seg=L[wIdx[k]+1:wIdx[k+1]]
        if seg: recovs.append(dict(t=sum(x["t"] for x in seg), d=sum(x["d"] for x in seg), hr=seg[0]["hr"]))
    if not recovs: return None
    rec_times=[r["t"] for r in recovs]
    if statistics.median(rec_times) < 15: return None
    if sum(r["d"] for r in recovs)/len(recovs) > workDist*0.7: return None
    reps=[x["t"] for x in works]
    valid=[r for r in reps if r>0]
    if len(valid)<2: return None
    detail=[]
    for i,w in enumerate(works):
        r=recovs[i] if i<len(recovs) else None
        hr_end_rec=hr_near(works[i+1]["start"]) if i+1<len(works) else None
        detail.append(dict(n=i+1,t_s=w["t"],dist_m=w["d"],hr_avg=w["hr"],hr_max=w["hrmax"],cad=w["cad"],
            step=w["step"],gct=w["gct"],vo=w["vo"],
            rec_s=round(r["t"]) if r else None, rec_hr=r["hr"] if r else None, hr_end_rec=hr_end_rec))
    iso=f"{y:04d}-{mo:02d}-{da:02d}"
    return dict(date=iso,year=y,month=mo,day=da,season=seasonOf(y,mo,da),source="garmin-fit",type="series",
        rep_distance_m=workDist,n_reps=len(works),interval_s=round(statistics.median(rec_times)),
        reps=[round(x,1) for x in reps],
        best_s=min(valid),worst_s=max(valid),mean_s=round(sum(valid)/len(valid),2),median_s=statistics.median(valid),
        total_dist_m=workDist*len(works),total_time_s=round(sum(reps),1),
        hr_avg=s.get("avg_heart_rate"),hr_max=s.get("max_heart_rate"),
        sub_sport=s.get("sub_sport"), rep_detail=detail)

def extract_fit(raw):
    """download_activity(ORIGINAL) devolve normalmente um .zip com o .fit lá dentro."""
    if not raw: return None
    if raw[:2]==b"PK":  # é um zip
        try:
            z=zipfile.ZipFile(io.BytesIO(raw))
            for name in z.namelist():
                if name.lower().endswith(".fit"):
                    return z.read(name)
        except Exception:
            return None
        return None
    return raw  # já é o próprio .fit

def load_json(name, default):
    p=os.path.join(DATA,name)
    if os.path.exists(p):
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default

def save_json(name, obj):
    json.dump(obj, open(os.path.join(DATA,name),"w",encoding="utf-8"),
              ensure_ascii=False, separators=(",",":"), default=str)

def main():
    email=os.environ.get("GARMIN_EMAIL"); pw=os.environ.get("GARMIN_PASSWORD")
    if not email or not pw:
        raise SystemExit("Faltam as secrets GARMIN_EMAIL / GARMIN_PASSWORD.")
    print("A entrar na conta Garmin…")
    g=Garmin(email, pw); g.login()

    dados=load_json("dados.json", {"meta":{},"workouts":[]})
    runs =load_json("runs.json",  {"meta":{},"cols":["date","dist_m","dur_s","type","hr"],"runs":[]})
    ann  =load_json("ann_defaults.json", {})
    state=load_json("state.json", {"last_date":"2020-01-01","processed":[]})
    processed=set(str(x) for x in state.get("processed",[]))

    start=state.get("last_date","2020-01-01")
    today=datetime.date.today().isoformat()
    print(f"A procurar atividades de {start} a {today}…")
    try:
        acts=g.get_activities_by_date(start, today)
    except Exception as e:
        print("Falha a listar atividades:", e); raise

    have_series=set(keyOf(w) for w in dados["workouts"])
    have_runs=set((r[0],r[1],r[2]) for r in runs["runs"])
    n_new_runs=0; n_new_series=0

    for a in acts:
        aid=str(a.get("activityId"))
        if aid in processed: continue
        tk=(a.get("activityType") or {}).get("typeKey","")
        stl=a.get("startTimeLocal") or a.get("startTimeGMT") or ""
        d=stl[:10]
        if tk in RUNMAP and len(d)==10:
            dist=a.get("distance") or 0      # metros (API)
            dur =a.get("duration") or 0      # segundos (API)
            hr  =a.get("averageHR")
            dist_m=round(dist); dur_s=round(dur)
            if dist_m>=300 and dur_s>=60 and (d,dist_m,dur_s) not in have_runs:
                runs["runs"].append([d,dist_m,dur_s,RUNMAP[tk], round(hr) if hr else None])
                have_runs.add((d,dist_m,dur_s)); n_new_runs+=1
            # reconstrução repetição a repetição a partir do FIT original
            try:
                raw=g.download_activity(aid, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
                fitb=extract_fit(raw)
                if fitb:
                    w=reconstruct(fitb)
                    if w and keyOf(w) not in have_series:
                        dados["workouts"].append(w); have_series.add(keyOf(w)); n_new_series+=1
                        if w.get("sub_sport") in ("treadmill","indoor_running"):
                            ann[keyOf(w)]={"objetivo":"Limiar 4 mmol","_auto":"passadeira"}
            except Exception as e:
                print(f"  (sem FIT utilizável para {aid}: {e})")
        processed.add(aid)

    # ordenar + reindexar
    dados["workouts"].sort(key=lambda w: w["date"])
    for i,w in enumerate(dados["workouts"],1): w["id"]=i
    dados["meta"]["n"]=len(dados["workouts"]); dados["meta"]["updated"]=today
    runs["runs"].sort(key=lambda r: r[0]); runs["meta"]["n"]=len(runs["runs"])

    state["last_date"]=today
    state["processed"]=sorted(processed)

    save_json("dados.json", dados)
    save_json("runs.json", runs)
    save_json("ann_defaults.json", ann)
    save_json("state.json", state)
    print(f"Feito. +{n_new_series} sessões de séries, +{n_new_runs} corridas. "
          f"Total: {len(dados['workouts'])} séries, {len(runs['runs'])} corridas.")

if __name__=="__main__":
    main()
