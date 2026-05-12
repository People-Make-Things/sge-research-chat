# SGE Research Chat

Next.js App Router chat interface for the Social Growth Engineers RAG index.

## Local Development

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:3000`.

For local Chroma fallback, run the Python API at `http://127.0.0.1:8000`:

```bash
cd ..
source .venv/bin/activate
sge-rag serve --reload
```

For Vercel production retrieval, set `SGE_VECTORSTORE=upstash`, `UPSTASH_VECTOR_REST_URL`, `UPSTASH_VECTOR_REST_TOKEN`, and `OPENAI_API_KEY`.

## Checks

```bash
npm run lint
npm run build
```
