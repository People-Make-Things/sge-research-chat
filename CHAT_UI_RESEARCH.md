# Chat UI Research

Goal: add a public, simple chat interface without rebuilding a full chat UI stack from scratch.

## Recommendation

Use `assistant-ui` for the first public interface.

Why:

- It is built specifically for production React AI chat interfaces and includes chat state, primitives, branching, editing, cancellation, and regeneration patterns.
- `@assistant-ui/react-ai-sdk` connects the same UI primitives directly to Vercel AI SDK streams.
- It keeps the public chat UI modern without forcing a full custom message/composer/source system.
- The Python pipeline can stay focused on ingestion and indexing while Next.js owns the public request path.

Sources:

- assistant-ui docs: https://www.assistant-ui.com/docs
- assistant-ui AI SDK runtime docs: https://www.assistant-ui.com/docs/runtimes/ai-sdk

## Alternatives Checked

`AI Elements` by Vercel is the best alternative if we want a shadcn/ui component registry rather than assistant-ui primitives. It gives more direct component ownership, but that also means more UI assembly.

Sources:

- Vercel AI Elements announcement: https://vercel.com/changelog/introducing-ai-elements
- AI Elements repo: https://github.com/vercel/ai-elements

`Vercel AI SDK` is the TypeScript model/streaming layer now used by the public `/api/chat` route. It streams retrieval status, source metadata, and answer tokens to assistant-ui.

Source:

- Vercel AI SDK 6: https://vercel.com/blog/ai-sdk-6

## Implemented Choice

This repo now uses:

- Next.js App Router + React 19 + TypeScript for the public frontend.
- `@assistant-ui/react` and `@assistant-ui/react-ai-sdk` for the thread, composer, streaming runtime, and source parts.
- Vercel AI SDK for `POST /api/chat` streaming.
- Upstash Vector as the production vector store, with Chroma/FastAPI kept as the local fallback.
