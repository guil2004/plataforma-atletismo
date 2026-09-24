#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sincronização automática Garmin -> plataforma de estímulos.
Corre todos os dias (GitHub Actions). Faz login na tua conta Garmin,
vai buscar as atividades novas desde a última sincronização, descarrega
o ficheiro FIT de cada corrida, reconstrói as sessões (repetição a
repetição, incluindo treinos compostos e testes de lactato Amândio) e
atualiza os dados do site.

Não precisas de mexer aqui. As credenciais vêm de duas "secrets" do
GitHub: GARMIN_EMAIL e GARMIN_PASSWORD.
"""
import os, io, json, zipfile, datetime, traceback
from garminconnect import Garmin
import engine   # motor v3: séries, blocos, compostos, testes Amândio

DATA = "data"
RUNMAP = {"running":"estrada","street_running":"estrada","trail_running":"trail",
          "treadmill_running":"passadeira","indoor_running":"passadeira",
          "track_running":"pista"}

def keyOf(w):
    """Chave única de uma sessão. TEM de coincidir com o keyOf do template.html."""
    t = w.get('type')
    if t == 'bloco':      kd = w.get('block_min') or ''
    elif t == 'composto': kd = w.get('label') or ''
    elif t == 'teste':    kd = w.get('test_name') or ''
    else:                 kd = w.get('rep_distance_m') or ''
    return f"{w['date']}#{t}#{kd}#{w.get('n_reps') or ''}"

def rebuild_ann(workouts):
    """Sugestão automática do objetivo fisiológico (o treinador pode alterar):
       - teste Amândio                    -> Teste de lactato
       - bloco por tempo                  -> Limiar individual
       - série/composto na passadeira     -> Limiar 4 mmol
       - série/composto na pista/exterior -> VO₂max
    """
    ann = {}
    for w in workouts:
        obj = None
        t = w.get('type')
        treadmill = w.get('sub_sport') in ('treadmill', 'indoor_running')
        if t == 'teste':
            obj = 'Teste de lactato'
        elif t == 'bloco':
            obj = 'Limiar individual'
        elif t in ('series', 'composto'):
            obj = 'Limiar 4 mmol' if treadmill else 'VO₂max'
        if obj:
            ann[keyOf(w)] = {'objetivo': obj, '_auto': True}
    return ann

def extract_fit(raw):
    """download_activity(ORIGINAL) devolve normalmente um .zip com o .fit lá dentro."""
    if not raw: return None
    if raw[:2] == b"PK":  # é um zip
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            for name in z.namelist():
                if name.lower().endswith(".fit"):
                    return z.read(name)
        except Exception:
            return None
        return None
    return raw  # já é o próprio .fit

def load_json(name, default):
    p = os.path.join(DATA, name)
    if os.path.exists(p):
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: return default
    return default

def save_json(name, obj):
    json.dump(obj, open(os.path.join(DATA, name), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"), default=str)

def main():
    email = os.environ.get("GARMIN_EMAIL"); pw = os.environ.get("GARMIN_PASSWORD")
    if not email or not pw:
        raise SystemExit("Faltam as secrets GARMIN_EMAIL / GARMIN_PASSWORD.")
    dados = load_json("dados.json", {"meta": {}, "workouts": []})
    runs  = load_json("runs.json",  {"meta": {}, "cols": ["date","dist_m","dur_s","type","hr"], "runs": []})
    state = load_json("state.json", {"last_date": "2020-01-01", "processed": []})
    processed = set(str(x) for x in state.get("processed", []))

    start = state.get("last_date", "2020-01-01")
    today = datetime.date.today().isoformat()
    have_series = set(keyOf(w) for w in dados["workouts"])
    have_runs = set((r[0], r[1], r[2]) for r in runs["runs"])
    n_new_runs = 0; n_new_series = 0
    garmin_ok = False

    # A ida ao Garmin pode falhar (ex.: 429 da Garmin). Se falhar, seguimos na
    # mesma para reclassificar e reconstruir o site com o que já há.
    try:
        print("A entrar na conta Garmin…")
        g = Garmin(email, pw); g.login()
        print(f"A procurar atividades de {start} a {today}…")
        acts = g.get_activities_by_date(start, today)
        for a in acts:
            aid = str(a.get("activityId"))
            if aid in processed: continue
            tk = (a.get("activityType") or {}).get("typeKey", "")
            stl = a.get("startTimeLocal") or a.get("startTimeGMT") or ""
            d = stl[:10]
            nm = (a.get("activityName") or "").strip() or None
            if tk in RUNMAP and len(d) == 10:
                dist = a.get("distance") or 0      # metros (API)
                dur  = a.get("duration") or 0      # segundos (API)
                hr   = a.get("averageHR")
                dist_m = round(dist); dur_s = round(dur)
                if dist_m >= 300 and dur_s >= 60 and (d, dist_m, dur_s) not in have_runs:
                    runs["runs"].append([d, dist_m, dur_s, RUNMAP[tk], round(hr) if hr else None])
                    have_runs.add((d, dist_m, dur_s)); n_new_runs += 1
                try:
                    raw = g.download_activity(aid, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
                    fitb = extract_fit(raw)
                    if fitb:
                        w = engine.reconstruct(fitb, nm)
                        if w and keyOf(w) not in have_series:
                            dados["workouts"].append(w); have_series.add(keyOf(w)); n_new_series += 1
                except Exception as e:
                    print(f"  (sem FIT utilizável para {aid}: {e})")
            processed.add(aid)
        garmin_ok = True
    except Exception as e:
        print("AVISO: não consegui sincronizar com o Garmin desta vez:", e)
        traceback.print_exc()
        print("Sigo na mesma para reconstruir com os dados existentes.")

    # reclassificar TODA a base de dados (sugestões automáticas)
    ann = rebuild_ann(dados["workouts"])

    # ordenar + reindexar
    dados["workouts"].sort(key=lambda w: w["date"])
    for i, w in enumerate(dados["workouts"], 1): w["id"] = i
    dados["meta"]["n"] = len(dados["workouts"]); dados["meta"]["updated"] = today
    runs["runs"].sort(key=lambda r: r[0]); runs["meta"]["n"] = len(runs["runs"])

    # Só avançamos a data se a sincronização correu bem.
    if garmin_ok:
        state["last_date"] = today
    state["processed"] = sorted(processed)

    save_json("dados.json", dados)
    save_json("runs.json", runs)
    save_json("ann_defaults.json", ann)
    save_json("state.json", state)
    from collections import Counter
    tipos = Counter(w.get("type") for w in dados["workouts"])
    print(f"Feito ({'Garmin OK' if garmin_ok else 'sem Garmin hoje'}). "
          f"+{n_new_series} sessões novas, +{n_new_runs} corridas novas. "
          f"Total: {dict(tipos)}, {len(runs['runs'])} corridas.")

if __name__ == "__main__":
    main()
