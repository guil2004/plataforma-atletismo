# Robô diário — plataforma de estímulos

Este robô vai à tua conta Garmin **todos os dias**, busca os treinos novos,
reconstrói as séries (repetição a repetição) e atualiza um site que só tens
de abrir. Depois de montado uma vez, **não te pede mais nada**.

É a mesma ideia do "caderno" que já montaste — GitHub + tarefa diária.
Segue os passos pela ordem. Não precisas de programar nada.

---

## O que está nesta pasta

- `index.html` — o site (já vem com todo o teu histórico: 470 séries + volume).
- `data/` — os dados (o robô atualiza-os sozinho).
- `sync.py` — o robô (login Garmin + reconstrução). **Não mexer.**
- `build_page.py` — reconstrói o site após cada sincronização. **Não mexer.**
- `template.html`, `requirements.txt`, `.github/workflows/sync.yml` — peças internas.

---

## Passo 1 — Criar o repositório no GitHub

1. Vai a **github.com** e entra na tua conta (a mesma do caderno serve).
2. Canto superior direito → **+** → **New repository**.
3. Nome à tua escolha, por exemplo `plataforma-atletismo`.
4. Deixa em **Public** (é preciso para o site gratuito funcionar).
5. Carrega em **Create repository**.

## Passo 2 — Carregar estes ficheiros

Na página do repositório novo:

1. Carrega em **uploading an existing file** (ou **Add file → Upload files**).
2. Arrasta para lá **tudo o que está nesta pasta** — incluindo a pasta `data`
   e a pasta `.github` (arrasta as pastas inteiras).
3. Em baixo, carrega em **Commit changes**.

> Se a pasta `.github` não aparecer ao arrastar (o Windows às vezes esconde-a),
> não faz mal: o site já funciona sem ela; só a atualização automática é que
> precisa dela. Nesse caso diz-me e envio-te outra forma de a colocar.

## Passo 3 — Dar as credenciais do Garmin ao robô (em segurança)

As tuas credenciais ficam guardadas **encriptadas** no GitHub, nunca no código.

1. No repositório, vai a **Settings** (no menu de cima).
2. Menu esquerdo: **Secrets and variables** → **Actions**.
3. Botão **New repository secret**:
   - **Name:** `GARMIN_EMAIL` — **Secret:** o teu email do Garmin → **Add secret**.
4. Outra vez **New repository secret**:
   - **Name:** `GARMIN_PASSWORD` — **Secret:** a tua palavra-passe do Garmin → **Add secret**.

## Passo 4 — Ligar o site

1. **Settings** → menu esquerdo **Pages**.
2. Em **Source**, escolhe **Deploy from a branch**.
3. Em **Branch**, escolhe **main** e a pasta **/ (root)** → **Save**.
4. Passado um minuto, no topo dessa página aparece o endereço do teu site:
   `https://O-TEU-UTILIZADOR.github.io/plataforma-atletismo/`
   Guarda esse link — é a tua plataforma. Já abre com todo o histórico.

## Passo 5 — Ligar a atualização diária (e a primeira sincronização)

1. No repositório, separador **Actions** (no menu de cima).
2. Se aparecer um aviso a pedir para ativar, carrega em
   **I understand my workflows, go ahead and enable them**.
3. À esquerda, escolhe **Sincronizar Garmin** → botão **Run workflow** →
   **Run workflow**. Isto corre o robô pela primeira vez e vai buscar tudo o
   que fizeste desde 15 de julho de 2026 (a data até onde o arquivo já tinha).
4. A partir daqui corre **sozinho todos os dias**.

Pronto. Abre o link do Passo 4 sempre que quiseres ver os teus treinos.

---

## Perguntas rápidas

**Tenho de fazer alguma coisa todos os dias?** Não. O robô trata de tudo.

**E os treinos de hoje aparecem quando?** Na sincronização seguinte (uma vez
por dia). Se quiseres ver logo, vai a **Actions → Sincronizar Garmin → Run
workflow**.

**A reconstrução repetição a repetição continua a funcionar nos treinos novos?**
Sim — o robô descarrega o ficheiro completo (FIT) de cada corrida, por isso as
séries novas entram já com tempo, FC e recuperação de cada repetição.

**As séries de passadeira continuam a ser marcadas como Limiar 4 mmol?** Sim,
automaticamente, como combinámos. As classificações que fizeres à mão mantêm-se.

**A sincronização falhou (login).** Quase sempre é a verificação em dois passos
(2FA) da Garmin a bloquear o robô. É o mesmo do caderno — se lá resolveste,
resolve-se igual aqui. Se precisares, diz-me e vemos juntos.
