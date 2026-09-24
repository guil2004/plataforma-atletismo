# -*- coding: utf-8 -*-
"""Motor v3: base conservadora (como a versão aceite) + compostos + testes amandio + nomes."""
import statistics
from garmin_fit_sdk import Decoder, Stream
from collections import Counter

NICE=[100,150,200,300,400,500,600,800,1000,1200,1500,2000,3000,5000]
def snap(d):
    if not d: return None
    return min(NICE, key=lambda x: abs(x-d))
def seasonOf(y,m,d):
    if m>=9 or (m==8 and d>=25): return f"{y}/{y+1}"
    return f"{y-1}/{y}"
def cad(l):
    c=l.get('avg_running_cadence')
    if c is None: c=l.get('avg_cadence')
    if c is None: return None
    return round((c+(l.get('avg_fractional_cadence') or 0))*2)

def _laps(msgs):
    L=[]
    for l in msgs.get('lap_mesgs',[]):
        d=round(l.get('total_distance') or 0)
        t=round((l.get('total_timer_time') or l.get('total_elapsed_time') or 0),1)
        L.append(dict(d=d,t=t,hr=l.get('avg_heart_rate'),hrmax=l.get('max_heart_rate'),cad=cad(l),
            step=round(l.get('avg_step_length')) if l.get('avg_step_length') else None,
            gct=round(l.get('avg_stance_time')) if l.get('avg_stance_time') else None,
            vo=round(l.get('avg_vertical_oscillation'),1) if l.get('avg_vertical_oscillation') else None,
            start=l.get('start_time'),
            pace=(round((l.get('total_timer_time') or 0)/((l.get('total_distance') or 1)/1000)) if (l.get('total_distance') or 0)>0 else 99999)))
    return L
def _hr_series(msgs):
    s=[(r.get('timestamp'),r.get('heart_rate')) for r in msgs.get('record_mesgs',[]) if r.get('timestamp') and r.get('heart_rate') is not None]
    s.sort(key=lambda x:x[0]); return s
def _hr_near(series,ts):
    if not ts or not series: return None
    best=None;bd=1e9
    for t,h in series:
        dd=abs((t-ts).total_seconds())
        if dd<bd:bd=dd;best=h
    return best if bd<15 else None
def _detail(laps, series):
    out=[]
    for i,w in enumerate(laps):
        hr_end_rec=_hr_near(series, laps[i+1]['start']) if i+1<len(laps) else None
        out.append(dict(n=i+1,t_s=w['t'],dist_m=w['d'],hr_avg=w['hr'],hr_max=w['hrmax'],cad=w['cad'],
            step=w['step'],gct=w['gct'],vo=w['vo'],hr_end_rec=hr_end_rec))
    return out

def reconstruct(fit_bytes, name=None):
    try:
        msgs,_=Decoder(Stream.from_byte_array(bytearray(fit_bytes))).read()
    except Exception:
        return None
    return reconstruct_msgs(msgs, name)

def reconstruct_msgs(msgs, name=None):
    sess=msgs.get('session_mesgs') or []
    if not sess: return None
    s=sess[0]
    if s.get('sport')!='running': return None
    L=_laps(msgs)
    if len(L)<3: return None
    start=s.get('start_time')
    if not start: return None
    y,mo,da=start.year,start.month,start.day
    iso=f"{y:04d}-{mo:02d}-{da:02d}"
    series=_hr_series(msgs)
    base=dict(date=iso,year=y,month=mo,day=da,season=seasonOf(y,mo,da),source='garmin-fit',
        sub_sport=s.get('sub_sport'), garmin_name=(name or None),
        hr_avg=s.get('avg_heart_rate'), hr_max=s.get('max_heart_rate'))

    # ---------- TESTE AMANDIO (nome + patamares ~5min) ----------
    if name and 'amandio' in name.lower():
        stg=[x for x in L if x['d']>=600 and 240<=x['t']<=380]   # patamares ~5min
        if len(stg)>=3:
            ts=[x['t'] for x in stg]
            base.update(type='teste', test_name='Amandio', n_reps=len(stg),
                reps=[round(t,1) for t in ts], rep_detail=_detail(stg,series),
                best_s=min(ts), worst_s=max(ts), mean_s=round(sum(ts)/len(ts),2), median_s=statistics.median(ts),
                total_time_s=round(sum(ts),1), interval_s=None)
            return base

    # ---------- base conservadora: grupo principal por distância ----------
    counts=Counter(snap(x['d']) for x in L if x['d'] and snap(x['d']))
    if not counts: return None
    workDist=max([k for k,_ in counts.most_common(2)])
    isW=lambda x: snap(x['d'])==workDist and x['d']>=100
    works0=[x for x in L if isW(x)]
    if len(works0)<2: return None
    med=statistics.median([w['t'] for w in works0])
    keep=set(id(w) for w in works0 if 0.5*med<=w['t']<=1.7*med)
    works=[x for x in L if id(x) in keep]
    if len(works)<2: return None
    wset=set(id(w) for w in works)
    wIdx=[i for i,x in enumerate(L) if id(x) in wset]
    recovs=[]
    for k in range(len(wIdx)-1):
        seg=L[wIdx[k]+1:wIdx[k+1]]
        if seg: recovs.append(dict(t=sum(x['t'] for x in seg), d=sum(x['d'] for x in seg)))
    if not recovs: return None
    rec_t=[r['t'] for r in recovs]
    if statistics.median(rec_t)<15: return None
    if sum(r['d'] for r in recovs)/len(recovs) > workDist*0.7: return None
    interval=round(statistics.median(rec_t))
    prim_pace=statistics.median([w['pace'] for w in works])

    # bloco por tempo?
    is_block = (round(med/60)>=6) or (workDist>=2000)

    # ---------- procurar grupo(s) secundário(s) (compostos) ----------
    extra=[]
    if not is_block:
        used=set(id(w) for w in works)
        # candidatos: laps rápidos (ritmo perto do trabalho) que não são do grupo principal
        cand=[x for x in L if id(x) not in used and x['d']>=100 and x['pace']<prim_pace*1.4 and snap(x['d'])!=workDist]
        by=Counter(snap(x['d']) for x in cand)
        for sd,c in by.items():
            if c>=2:
                gl=[x for x in cand if snap(x['d'])==sd]
                gt=[x['t'] for x in gl]
                if max(gt)/max(1,min(gt))>=1.8: continue          # tempos muito díspares -> não é um set
                # rejeitar contaminação: reps do set principal que ficaram curtas/longas
                # (a distância REAL fica perto da principal, ao contrário de um set genuíno mais curto)
                med_raw=statistics.median([x['d'] for x in gl])
                if abs(med_raw-workDist) <= 0.22*workDist: continue
                extra.append((sd,gl))

    def seg_from(dist, laps):
        laps=sorted(laps, key=lambda x: L.index(x))
        ts=[w['t'] for w in laps]
        return dict(kind='dist', value=dist, n_reps=len(laps),
            reps=[round(t,1) for t in ts], detail=_detail(laps,series),
            best_s=min(ts), worst_s=max(ts), mean_s=round(sum(ts)/len(ts),2), median_s=statistics.median(ts))

    if extra:
        primary=seg_from(workDist, works)
        segs=[primary]+[seg_from(sd,gl) for sd,gl in extra]
        # ordenar pela ordem de aparição
        segs.sort(key=lambda g: min(L.index(x) for x in ([w for w in works] if g is primary else [x for x in L if snap(x['d'])==g['value'] and id(x) not in wset and x['pace']<prim_pace*1.4])))
        def lbl(g): return f"{g['n_reps']}×{g['value']}"
        allt=[t for g in segs for t in g['reps'] if t]
        base.update(type='composto', segments=segs, label=' + '.join(lbl(g) for g in segs),
            dists=sorted(set(g['value'] for g in segs)),
            total_dist_m=sum(g['n_reps']*g['value'] for g in segs),
            interval_s=interval, total_time_s=round(sum(allt),1))
        return base

    # ---------- simples: série ou bloco ----------
    reps=[w['t'] for w in works]; valid=[r for r in reps if r>0]
    common=dict(n_reps=len(works), interval_s=interval, reps=[round(r,1) for r in reps],
        rep_detail=_detail(works,series), best_s=min(valid), worst_s=max(valid),
        mean_s=round(sum(valid)/len(valid),2), median_s=statistics.median(valid),
        total_time_s=round(sum(reps),1))
    if is_block:
        base.update(type='bloco', block_min=round(med/60), **common)
    else:
        base.update(type='series', rep_distance_m=workDist, total_dist_m=workDist*len(works), **common)
    return base
