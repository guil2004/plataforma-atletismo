#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constrói o index.html a partir do template + dos dados em data/.
Corre depois do sync.py. Não precisas de mexer aqui."""
import re

def inject(html, tag_id, path):
    data = open(f"data/{path}", encoding="utf-8").read().strip()
    return re.sub(r'(<script id="'+tag_id+r'" type="application/json">).*?(</script>)',
                  lambda m: m.group(1)+data+m.group(2), html, count=1, flags=re.S)

def main():
    h = open("template.html", encoding="utf-8").read()
    h = inject(h, "demo", "dados.json")
    h = inject(h, "runs", "runs.json")
    h = inject(h, "anndefaults", "ann_defaults.json")
    # No site automático, os dados embebidos (atualizados pelo robô) são a fonte:
    # não deixar o localStorage esconder a versão nova.
    h = h.replace("load(LS.data,null)||demo.workouts", "demo.workouts")
    h = h.replace("isDemo: !load(LS.data,null)", "isDemo: false")
    open("index.html", "w", encoding="utf-8").write(h)
    print("index.html construído.")

if __name__ == "__main__":
    main()
