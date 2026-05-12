# Social Growth Engineers RAG

Greenfield RAG pipeline for Social Growth Engineers article content.

It can ingest through normal HTTP when the site is publicly reachable, or through a real browser session when Vercel/auth requires a logged-in browser.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
cp .env.example .env
```

Add `OPENAI_API_KEY` to `.env`.

## Login For Browser-Authenticated Fetching

If terminal requests hit the Vercel security checkpoint or you need private/member content:

```bash
sge-rag login
```

A Chromium window opens. Log in to Social Growth Engineers, then press Enter in the terminal. This writes `data/browser_state.json`, which ingestion can reuse.

## Ingest

Start with a small smoke test:

```bash
sge-rag ingest --limit 10 --fetcher auto
```

Full ingestion:

```bash
sge-rag ingest --fetcher auto
```

If HTTP gets blocked, use:

```bash
sge-rag ingest --fetcher browser
```

Raw normalized articles are written to `data/articles/`, the manifest to `data/manifest.json`, and Chroma to `data/chroma/` by default.

For public Vercel retrieval, configure Upstash Vector and backfill the saved article chunks:

```bash
SGE_VECTORSTORE=upstash sge-rag backfill-vectors --vectorstore upstash
```

## Query

```bash
sge-rag query "Instagram Reels strategy from recent articles" --top-k 6
```

Filter by category and date:

```bash
sge-rag query "finance TikTok hooks" --category strategy --after 2026-01-01
```

## API

```bash
sge-rag serve --reload
```

Endpoints:

- `GET /health`
- `POST /ingest`
- `POST /query`
- `POST /retrieve`

Example:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Instagram Reels strategy from recent articles","top_k":5}'
```

## Web App

The public app interface lives in `web/` and uses Next.js App Router, Vercel AI SDK streaming, `@assistant-ui/react-ai-sdk`, and `@assistant-ui/react`.

For local Chroma retrieval, run the API in one terminal:

```bash
source .venv/bin/activate
sge-rag serve --reload
```

Run the frontend dev server:

```bash
cd web
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The Next `/api/chat` route streams model output and uses Fast mode (`gpt-5.4-mini`) by default, with Deep mode (`gpt-5.5`) opt-in.

For Vercel, set these environment variables on the project:

```bash
OPENAI_API_KEY=...
SGE_VECTORSTORE=upstash
UPSTASH_VECTOR_REST_URL=...
UPSTASH_VECTOR_REST_TOKEN=...
SGE_FAST_MODEL=gpt-5.4-mini
SGE_DEEP_MODEL=gpt-5.5
```

See `CHAT_UI_RESEARCH.md` for the chat-library decision. Short version: `assistant-ui` was chosen because it provides the thread, composer, cancellation, and source primitives while `@assistant-ui/react-ai-sdk` connects directly to the Vercel AI SDK stream.

## Public Deployment

Vercel is now the public app target. Deploy the `web/` directory as a Next.js project, set the environment variables above, and keep the Python service for ingestion/admin jobs. The public `POST /api/chat` route does not need FastAPI when `SGE_VECTORSTORE=upstash`.

Docker remains useful for local/internal FastAPI compatibility:

```bash
docker build -t sge-rag-public .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  sge-rag-public
```

Deploy the Docker image to a public container host such as Fly.io, Render, Railway, or a VPS. Set `OPENAI_API_KEY` as a platform secret.

The Docker image copies `data/chroma` so the current index must exist before building. `.dockerignore` excludes `.env`, `.venv`, article JSON, manifests, and `data/browser_state.json`.

## Notes

- The default embedding model is `text-embedding-3-small`.
- The default fast answer model is `gpt-5.4-mini`; Deep mode uses `gpt-5.5`.
- For local parser/chunking tests without OpenAI, use `SGE_EMBEDDING_PROVIDER=hash`.
