# LectureMind Frontend

React 19 + TypeScript single-page application for the LectureMind platform, served by nginx in production.

---

## Stack

| | |
|---|---|
| **Framework** | React 19 + TypeScript |
| **UI Library** | Ant Design 6 |
| **Styling** | Tailwind CSS |
| **Video Player** | @mux/mux-video-react (HLS adaptive streaming) |
| **Mindmap** | @xyflow/react (ReactFlow) |
| **Routing** | React Router v7 |
| **Package manager** | pnpm |

---

## Development

```bash
# Install dependencies
pnpm install

# Start dev server on http://localhost:3000
pnpm start

# Production build
pnpm build

# Run tests
pnpm test
```

### Configuring the API URL

The backend API URL is read from `window.__ENV__.API_PREFIX` (injected at
container start in Docker). During local development it falls back to the
static file `public/env-config.js`:

```js
// public/env-config.js
window.__ENV__ = { API_PREFIX: "http://127.0.0.1:8000" };
```

Edit this file if your backend runs on a different host or port. It is
**not** committed with secrets — changes are local only.

---

## Docker

The frontend is built and served as part of the root `docker-compose.yml`.
You do not need to run anything manually for production; see the root
[README](../README.md#quick-start-docker).

To build and run the frontend container on its own:

```bash
# From repo root
docker build -t lecturemind-frontend ./frontend

docker run -p 3000:3000 \
    -e API_PREFIX=http://localhost:8000 \
    lecturemind-frontend
```

`API_PREFIX` is written into `env-config.js` at container startup by
`docker-entrypoint.sh`, so no rebuild is needed to point the app at a
different backend.

---

## Project Structure

```
frontend/
├── Dockerfile                  # 2-stage: node builder + nginx:1.27-alpine
├── docker-entrypoint.sh        # writes env-config.js → starts nginx
├── nginx/default.conf          # SPA routing, cache headers
├── public/
│   ├── index.html              # loads env-config.js at runtime
│   └── env-config.js           # default API URL for local dev
└── src/
    ├── config.ts               # API_PREFIX, supported LLM models
    ├── model.tsx               # shared TypeScript interfaces
    ├── MainLayout.tsx          # sidebar + routing
    ├── index.tsx               # app entry point
    ├── page/
    │   ├── UploadDashboard.tsx     # drag-and-drop video upload
    │   ├── VideoDashboard.tsx      # video library grid
    │   ├── CourseDashboard.tsx     # course/episode management
    │   ├── TaskDashboard.tsx       # async task status monitor
    │   └── LectureVideoAnalysis.tsx# main analysis page (player + tabs)
    └── components/
        ├── ChatPanel.tsx           # chat message list + input
        ├── ThinkingPanel.tsx       # agent reasoning step visualiser
        └── lecture/
            ├── StreamVideo.tsx         # HLS player wrapper
            ├── LectureTranscripts.tsx  # clickable sentence transcript
            ├── LectureSections.tsx     # sections/chapters panel
            ├── LectureChatbot.tsx      # RAG chatbot (SSE streaming)
            ├── LectureKnowledge.tsx    # knowledge points browser
            ├── LectureMindmap.tsx      # interactive concept map
            └── CourseCreationModal.tsx
```
