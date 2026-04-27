# Local Run Playbook — Team 07

This is a numbered terminal recipe for getting the AI Hub container running on your laptop. Run each block, check the verification output, then move on.

Folder layout we're assuming:
- Image (extracted): `<your folder>/Intersystems/`  (the `blobs/`, `manifest.json`, `oci-layout`, `repositories` files)
- Repo (already placed): `<your folder>/Intersystems/ready-2026-team-07/`

Replace `<your folder>` with whatever you selected when you set up Cowork (e.g. `~/Documents/`, `~/Desktop/`, etc).

---

## 0. Prerequisites

```bash
docker --version
docker compose version    # or: docker-compose --version
```

If either is missing, install Docker Desktop and re-open this playbook.

---

## 1. Load the IRIS image into Docker

The folder you have is the **extracted** form of the docker save. Docker can't read it as a directory — you need to stream it back as a tar.

First check if it's already loaded:

```bash
docker images | grep irishealth-community
```

If you see `2026.2.0AI.158.0`, skip to step 2.

Otherwise, load it (this streams ~5 GB; takes a few minutes):

```bash
cd "<your folder>/Intersystems"
tar -cC . . | docker load
```

You should see lines like `Loaded image: docker.iscinternal.com/docker-intersystems/intersystems/irishealth-community:2026.2.0AI.158.0`.

Verify:

```bash
docker images | grep irishealth-community
# expected: docker.iscinternal.com/docker-intersystems/intersystems/irishealth-community   2026.2.0AI.158.0   ...
```

> **Mac (Apple Silicon) note:** if you downloaded the `arm64` build instead, the tag will be different. Edit `ready-2026-team-07/Dockerfile` line 1 to match `docker images` output before step 2.

---

## 2. Build the team container

```bash
cd "<your folder>/Intersystems/ready-2026-team-07"
docker compose up -d --build
```

This step:
- Spins IRIS, installs IPM (zpm), creates the `IRISAPP` namespace
- Loads `App.Installer.cls`, seeds `Sample.Person`
- ZPM-loads the `Sample.*` classes from `src/`
- Auto-runs `Sample.MCPSetup.Run()` to register the MCP web app at `/mcp/sample`

Build is ~3–6 min the first time. Check it's healthy:

```bash
docker compose ps                        # 'iris' should be running
docker compose logs --tail=80 iris       # look for "Started IRIS"
```

Open the Management Portal: <http://localhost:52773/csp/sys/UtilHome.csp>  (login: `SuperUser` / `SYS`).

---

## 3. Smoke-test the agent (uses OpenAI)

```bash
docker compose exec iris iris session iris
```

In the IRIS terminal:

```objectscript
zn "IRISAPP"
set agent = ##class(Sample.Agent).%New()
set sc = agent.%Init()
write:sc'=1 $SYSTEM.Status.GetErrorText(sc), !
set session = agent.CreateSession()
set response = agent.Chat(session, "Add a person named Alice aged 30, and then get people younger than 35.")
write response.content
```

Expected: a natural-language reply confirming Alice was added and listing the people <35 (Peter 24, Amy 32, Zahra 28, Alice 30).

If you get `OPENAI_API_KEY is not set`: `.env` wasn't picked up — `docker compose down && docker compose up -d` to reload env.
Halt the session with `halt`.

---

## 4. Smoke-test the MCP server

The MCP web app is up, but its transport (the `iris-mcp-server` Rust binary) isn't running yet. Start it inside the container:

```bash
docker compose exec iris bash
iris-mcp-server -c config.toml run
```

Leave that terminal open (it logs every MCP request).

In a **second terminal** on your laptop:

```bash
cd "<your folder>/Intersystems/ready-2026-team-07"
pip install langchain-mcp-adapters       # add --user or use a venv if needed
python test_mcp.py
```

Expected output:

```
-  mcp_sample_AddPerson
-  mcp_sample_GetPeopleYoungerThan
-  mcp_sample_multiply
Available MCP tools:
[ ... rows < 30 ... ]
35
```

That confirms: IRIS-native query tool + ObjectScript method tool + Python stdio MCP child, all reachable through one HTTP MCP endpoint.

---

## 5. Stop / restart

```bash
# stop everything
docker compose down

# stop but keep the image+volume cache (faster restart)
docker compose stop

# resume
docker compose start

# rebuild after editing src/*.cls (re-runs iris.script and IPM load)
docker compose up -d --build
```

> Editing `.cls` files: VS Code with the InterSystems ObjectScript extension will hot-sync changes via the devcontainer config in `.devcontainer/devcontainer.json`. Otherwise, full rebuild.

---

## Common gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop not running | Start Docker Desktop |
| Build fails with `image not found` | Image tag mismatch | `docker images \| grep iris` then update `Dockerfile` line 1 |
| `OPENAI_API_KEY is not set` in agent test | `.env` not loaded | Ensure `.env` exists in the same dir as `docker-compose.yml`; restart compose |
| Port 52773 / 1972 / 8080 in use | Another service | Edit `docker-compose.yml` left-side ports (e.g. `52774:52773`) |
| `iris-mcp-server` says `connection refused` | Wrong creds in `config.toml` | Default `SuperUser`/`SYS` should work; check `iris session` works first |
| Agent reply "Failed to create provider 'openai'" | Bad/expired key | Rotate key on OpenAI dashboard, update `.env`, `docker compose down && up -d` |

---

## What's running where

| Component | URL / Path | Notes |
|---|---|---|
| IRIS Management Portal | http://localhost:52773/csp/sys/UtilHome.csp | `SuperUser` / `SYS` |
| MCP Service (CSP web app) | http://localhost:52773/mcp/sample/v1/services | Lists tools |
| MCP HTTP transport | http://localhost:8080/mcp/sample | Where MCP clients connect |
| IRIS SuperServer | localhost:1972 | For VS Code / `iris.connect()` |

---

## Next moves once it's all green

When all four checkpoints above pass, tell me what to build. The `Sample.*` package is a fully-working baseline you can either replace or extend. Most projects on this stack pivot one of:

- the **data model** — swap `Sample.Person` for your domain (FHIR, finance, your own tables)
- the **toolset** — add tools that wrap your data, an external API, or a sub-MCP
- the **agent shape** — multi-turn chat, sub-agent decomposition, RAG-grounded retrieval
- the **client surface** — Streamlit/Next/Chrome extension calling the MCP server, or wire it to Claude Desktop directly
