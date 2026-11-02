# Adani · The North Park, Villa Progress Platform

A single-page, offline-capable **interactive 3D villa** (Babylon.js, WebGPU with WebGL
fallback) **plus** an optional **Blender photorealistic render service**. Both show the
same villa, modelled in code in `blender/villa_render.py`: the web app loads a stage-aware
export of it, and the render service path-traces stills of it on demand. Each zone's
construction stage (Foundation → Structure → Finishing → Ready) drives what is shown.

```
Browser (Babylon.js interactive)  ──tap "Photoreal"──►  Node render API  ──spawns──►  Blender (bpy)
   dist/index.html                                        server/server.js           blender/villa_render.py
        ▲  interactive, offline                               │ job queue + status         │ procedural geometry,
        └───────────── shows rendered PNG ◄──/renders/*.png───┘                            └ materials, lights, camera
```

## Project structure

```
.
├── src/                        Web app source (edit here)
│   ├── index.html              Markup: login · villa directory · 3D experience
│   ├── css/
│   │   ├── fonts.css           @font-face declarations
│   │   └── main.css            Design tokens + all component styles
│   ├── js/                     Loaded in this order, concatenated at build time
│   │   ├── data.js             Villa data model (single source of truth) + validation
│   │   ├── ui.js               Header, progress ring, timeline, attention list
│   │   ├── drawer.js           Zone detail drawer
│   │   ├── render-studio.js    Photoreal (Blender) render modal
│   │   ├── scene-controls.js   Floor explorer, camera presets, reveal, evening
│   │   ├── scene.js            Babylon.js villa scene (WebGPU + WebGL fallback)
│   │   └── app.js              Screen flow: login → directory → villa
│   ├── assets/villa/           Villa exported from Blender (`npm run export:web`):
│   │                           scene.json (geometry per zone × stage), textures,
│   │                           plant sprites, sky HDRIs/panoramas
│   ├── fonts/                  Archivo, Outfit, Poppins (woff2)
│   └── vendor/babylon.js       Babylon.js v7 (bundled for offline use)
├── dist/                       Build output, deployed to Vercel
│   ├── index.html              Self-contained single file (generated, do not edit)
│   └── vercel.json
├── server/server.js            Static host + Blender render API (Node built-ins only)
├── blender/
│   ├── villa_render.py         The villa model: photoreal render, or `--export-web`
│   ├── fetch_assets.py         Downloads CC0 textures/HDRIs/plants from Poly Haven
│   └── assets/                 Downloaded assets (git-ignored, `npm run assets`)
├── scripts/
│   └── build.js                src/ → dist/index.html
├── assets/reference/           Architect reference renders (design reference only)
│   ├── exterior/
│   └── interior/
└── renders/                    Blender output (runtime, git-ignored)
```

## Develop

```bash
npm run assets      # one-off: download CC0 Poly Haven assets into blender/assets/
npm run export:web  # Blender → src/assets/villa/ (re-run after changing the villa model)
npm run build       # src/ → dist/index.html
npm start           # serve dist/ + render API on http://localhost:8770
npm run dev         # build, then start
npm run deploy      # build, then `vercel --prod` from dist/
```

The villa is designed in one place, `blender/villa_render.py`. After changing it, run
`npm run export:web` and `npm run build`; the exported `src/assets/villa/` is committed,
so a plain `npm run build` works without Blender.

Edit files in `src/`, never `dist/index.html`. Append `?webgl` to the URL to force the
WebGL backend instead of WebGPU.

## Requirements

- **macOS** (Apple Silicon), the target platform.
- **Node.js 18+** (tested on v24). No npm packages required.
- **Blender 5.x**, *optional*, only for photoreal renders (tested on 5.2.3 LTS; the render
  script stays compatible with 4.2+). The interactive 3D view needs no Blender.
- Cycles renders on the Apple GPU via **Metal** automatically. An EEVEE "fast" mode is also available.

## Install Blender

```bash
brew install --cask blender     # installs /Applications/Blender.app
```

The server auto-detects `/Applications/Blender.app` and `~/Applications/Blender.app`
(plus common Linux paths for server deployments). Override with `BLENDER_PATH` if
Blender lives elsewhere.

The first Cycles render after installing or updating Blender compiles the Metal GPU
kernels and takes ~2–3 minutes; later renders take seconds (≈14 s for 800×500 @ 64 samples
on Apple Silicon).

Then restart the server. `GET /api/render` reports `blenderAvailable` and the resolved path.

## Run

```bash
npm run dev
# -> http://localhost:8770/
```

Open **http://localhost:8770/** (not `file://`, so the render API is reachable). Use the
3D scene as normal; click **Photoreal** (top-right of the canvas) to generate a render.
If Blender is missing or you opened a `file://` page, the panel explains what to do and the
interactive view keeps working.

### Environment variables
| Var | Default | Meaning |
|---|---|---|
| `PORT` | `8770` | HTTP port |
| `BLENDER_PATH` | auto-detect | explicit path to the Blender binary |

## Render API

| Method · Path | Purpose |
|---|---|
| `GET /api/render` | `{ blenderAvailable, blenderPath, busy, queued }` |
| `POST /api/render` | body `{ view, engine, samples, res, zones }` → `{ jobId }` (202) |
| `GET /api/render/:jobId` | `{ status, message, progress, image, error, ms }` (`status`: queued·rendering·done·error) |
| `GET /renders/<id>.png` | the rendered image |

`view` = hero·front·aerial·pool · `engine` = CYCLES·EEVEE · `samples` 16–512 ·
`res` = `WxH` · `zones` = `{ groundFloor:{stage}, firstFloor:{stage}, … }` (drives
completed/in-progress/pending appearance). Jobs run one at a time (simple queue).

## How a render is produced (code-driven)

1. The page POSTs the current `villaData` zone stages to `/api/render`.
2. The server writes the zones to `renders/<id>.json` and runs:
   `blender -b -P blender/villa_render.py -- --out renders/<id>.png --engine … --data …`
3. `villa_render.py` (`bpy`) resets to an empty scene, builds the villa, walls, floors,
   roof, glazing, balconies, pool, landscaping, furniture, exterior lamps, assigns PBR
   materials, a Nishita sky + sun + fill light, places a camera for the chosen view, enables
   GPU (or CPU fallback) + denoising, and calls `bpy.ops.render.render(write_still=True)`.
4. The PNG lands in `renders/` and is served at `/renders/<id>.png`; the page displays it.

Construction stage changes the geometry/materials: e.g. a *Structure* first floor renders as
an exposed concrete frame, *Finishing/Ready* as finished terracotta; *Foundation* zones show
slabs/rebar.

## Deployment (server-side rendering)

For a shared/production setup, run on a Linux host (optionally GPU):

- Install Blender (`snap install blender --classic`) and Node.
- `BLENDER_PATH=/snap/bin/blender PORT=8080 npm start` behind nginx/Caddy.
- GPU box (NVIDIA): Blender auto-selects OptiX/CUDA; otherwise CPU still works (slower).
- Persist/clean `renders/`; the queue serialises jobs, scale with multiple workers/instances
  if you need concurrency.
- Keep-alive: run under `systemd`/`pm2` (Linux) or a `launchd` agent (macOS).

## Notes / limitations

- Cycles stills take seconds (GPU) to a few minutes (CPU) depending on samples/resolution.
- Renders are **not** a replacement for the interactive geometry, they complement it.
- The self-contained `dist/index.html` still opens offline; only the Photoreal
  feature needs the server + Blender.
