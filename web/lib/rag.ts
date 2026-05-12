import "server-only"
import "./env"

import { openai } from "@ai-sdk/openai"
import { Index } from "@upstash/vector"
import { embed } from "ai"

export type ChatMode = "fast" | "deep"

export type ResearchSource = {
  title: string
  source_url: string
  slug: string
  published_at: string | null
  categories: string[]
  chunk_id: string
  score: number | null
}

export type RetrievedChunk = {
  id: string
  text: string
  score: number | null
  metadata: {
    title?: string
    source_url?: string
    slug?: string
    published_at?: string
    categories?: string[]
    categories_json?: string
    [key: string]: unknown
  }
}

type UpstashMetadata = {
  title?: string
  source_url?: string
  slug?: string
  published_at?: string
  categories_json?: string
  [key: string]: unknown
}

type RetrieveResponse = {
  sources: ResearchSource[]
  chunks: RetrievedChunk[]
}

export function normalizeMode(mode: unknown): ChatMode {
  return mode === "deep" ? "deep" : "fast"
}

export function modelForMode(mode: ChatMode) {
  return mode === "deep"
    ? process.env.SGE_DEEP_MODEL || "gpt-5.5"
    : process.env.SGE_FAST_MODEL || "gpt-5.4-mini"
}

export function topKForMode(mode: ChatMode) {
  return mode === "deep" ? 8 : 4
}

function parseCategories(metadata: UpstashMetadata) {
  if (Array.isArray(metadata.categories)) return metadata.categories.filter((item) => typeof item === "string")
  if (!metadata.categories_json || typeof metadata.categories_json !== "string") return []
  try {
    const parsed = JSON.parse(metadata.categories_json)
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : []
  } catch {
    return []
  }
}

function asSource(chunk: RetrievedChunk): ResearchSource {
  return {
    title: String(chunk.metadata.title || "Untitled"),
    source_url: String(chunk.metadata.source_url || ""),
    slug: String(chunk.metadata.slug || ""),
    published_at: String(chunk.metadata.published_at || "") || null,
    categories: Array.isArray(chunk.metadata.categories)
      ? chunk.metadata.categories
      : parseCategories(chunk.metadata as UpstashMetadata),
    chunk_id: chunk.id,
    score: chunk.score,
  }
}

export function uniqueSources(sources: ResearchSource[]) {
  const seen = new Set<string>()
  return sources.filter((source) => {
    const key = source.source_url || source.slug || source.chunk_id
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function configuredVectorStore() {
  const configured = (process.env.SGE_VECTORSTORE || "").toLowerCase()
  if (configured === "chroma" || configured === "upstash") return configured
  return process.env.UPSTASH_VECTOR_REST_URL && process.env.UPSTASH_VECTOR_REST_TOKEN ? "upstash" : "chroma"
}

function trimText(text: string, maxChars: number) {
  if (text.length <= maxChars) return text
  return `${text.slice(0, Math.max(0, maxChars - 18)).trimEnd()}\n[trimmed]`
}

export function buildAnswerContext(chunks: RetrievedChunk[], mode: ChatMode) {
  const maxChunkChars = mode === "deep" ? 1800 : 1050
  const maxTotalChars = mode === "deep" ? 12000 : 5600
  let usedChars = 0
  const parts: string[] = []

  for (const [index, chunk] of chunks.entries()) {
    const source = asSource(chunk)
    const part = `[${index + 1}] ${source.title}
URL: ${source.source_url}
Date: ${source.published_at || ""}
Categories: ${source.categories.join(", ")}

${trimText(chunk.text, maxChunkChars)}`

    if (usedChars + part.length > maxTotalChars) {
      const remaining = maxTotalChars - usedChars
      if (remaining > 120) parts.push(trimText(part, remaining))
      break
    }
    parts.push(part)
    usedChars += part.length + 7
  }

  return parts.join("\n\n---\n\n")
}

async function retrieveFromUpstash(query: string, topK: number): Promise<RetrieveResponse> {
  const url = process.env.UPSTASH_VECTOR_REST_URL
  const token = process.env.UPSTASH_VECTOR_REST_TOKEN
  if (!url || !token) throw new Error("Upstash Vector is not configured.")

  const embeddingModel = process.env.SGE_EMBEDDING_MODEL || "text-embedding-3-small"
  const { embedding } = await embed({
    model: openai.embedding(embeddingModel),
    value: query,
  })

  const index = new Index<UpstashMetadata>({ url, token })
  const results = await index.query({
    vector: embedding,
    topK: Math.max(topK * 3, topK),
    includeMetadata: true,
    includeData: true,
  })

  const chunks = results.slice(0, topK).map((item) => {
    const metadata = item.metadata || {}
    const categories = parseCategories(metadata)
    return {
      id: String(item.id),
      text: item.data || "",
      score: item.score ?? null,
      metadata: {
        ...metadata,
        categories,
      },
    } satisfies RetrievedChunk
  })

  return { chunks, sources: uniqueSources(chunks.map(asSource)) }
}

async function retrieveFromFastApi(query: string, topK: number, mode: ChatMode): Promise<RetrieveResponse> {
  const baseUrl = (process.env.SGE_RAG_API_URL || process.env.RAG_API_BASE_URL || "http://127.0.0.1:8000").replace(
    /\/$/,
    "",
  )
  const response = await fetch(`${baseUrl}/retrieve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, mode }),
    cache: "no-store",
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Retrieval failed with ${response.status}`)
  }

  const data = (await response.json()) as RetrieveResponse
  return {
    chunks: data.chunks,
    sources: uniqueSources(data.sources),
  }
}

export async function retrieve(query: string, mode: ChatMode): Promise<RetrieveResponse & { store: string }> {
  const topK = topKForMode(mode)
  if (configuredVectorStore() === "upstash") {
    return { ...(await retrieveFromUpstash(query, topK)), store: "upstash" }
  }
  return { ...(await retrieveFromFastApi(query, topK, mode)), store: "chroma" }
}
