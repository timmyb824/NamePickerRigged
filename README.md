# Name Picker

A wheel-of-names style classroom spinner built for my wife who teaches elementary school. The teacher can secretly pre-select who the wheel lands on from a hidden admin page; the class-facing wheel page shows no trace of it.

## How it works

1. Visit `/` and create a wheel: title, names (one per line), admin password.
2. You get two links:
   - **Class view** `/w/<code>` — project this. Big wheel, SPIN button, winner popup.
   - **Admin page** `/w/<code>/admin` — password-protected. Edit names, and set
     the outcome: pick a winner and whether it applies to the **next spin only**
     or **every spin until cleared**.
3. The winner is always decided server-side, so a rigged spin looks identical
   to a random one in the page and its network traffic. Saving a new name list
   clears any rigged outcome (indexes shift).

Each wheel is fully independent — multiple teachers can each create their own.

## Local development

```sh
uv sync --all-extras
uv run pytest                       # tests
uv run uvicorn app.main:app --reload
```

## Container

```sh
podman build -t namepicker .        # or: docker build -t namepicker .
podman run -p 8000:8000 \
  -e SESSION_SECRET="$(openssl rand -hex 32)" \
  -v namepicker-data:/data \
  namepicker
```

Or `docker compose up` / `podman compose up` (set `SESSION_SECRET` first).

## Kubernetes notes

- Single container, listens on `:8000`. Point your Cloudflare Tunnel at the
  Service and you're done.
- **`SESSION_SECRET`**: set via a Secret, or admin logins reset on every
  restart.
- **Data**: wheels live in SQLite at `/data/wheels.db`. Mount a PVC at `/data`.
  Keep the Deployment at `replicas: 1` (SQLite is single-writer) — use a
  Recreate strategy if the PVC is ReadWriteOnce.
- Use a liveness/readiness probe on `GET /` instead of the image HEALTHCHECK.

## Environment variables

| Variable         | Default | Purpose                                  |
| ---------------- | ------- | ---------------------------------------- |
| `SESSION_SECRET` | random  | Signs admin session cookies              |
| `DATA_DIR`       | `data`  | Directory containing the SQLite database |
