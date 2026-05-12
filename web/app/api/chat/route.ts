import { openai } from "@ai-sdk/openai"
import { convertToModelMessages, createUIMessageStream, createUIMessageStreamResponse, streamText } from "ai"

import type { ResearchUIMessage } from "@/lib/chat-types"
import { buildAnswerContext, modelForMode, normalizeMode, retrieve } from "@/lib/rag"

export const runtime = "nodejs"
export const maxDuration = 60

const SYSTEM_PROMPT = `You answer from the provided Social Growth Engineers article context only.
If context is thin, say what is missing and give the best grounded next step.
Cite sources inline as [1], [2], etc. Keep the answer direct, practical, and specific.`

function textFromMessage(message: ResearchUIMessage) {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n")
    .trim()
}

function latestUserText(messages: ResearchUIMessage[]) {
  for (const message of [...messages].reverse()) {
    if (message.role !== "user") continue
    const text = textFromMessage(message)
    if (text) return text
  }
  return ""
}

export async function POST(request: Request) {
  const body = (await request.json()) as { messages?: ResearchUIMessage[]; mode?: unknown }
  const messages = Array.isArray(body.messages) ? body.messages : []
  const mode = normalizeMode(body.mode)
  const query = latestUserText(messages)

  const stream = createUIMessageStream<ResearchUIMessage>({
    originalMessages: messages,
    async execute({ writer }) {
      if (!query) {
        writer.write({
          type: "data-status",
          id: "status",
          data: { stage: "done", label: "Ask a strategy question to start.", mode },
        })
        return
      }

      writer.write({
        type: "data-status",
        id: "status",
        transient: true,
        data: { stage: "retrieving", label: "Searching the SGE library...", mode },
      })

      const retrieval = await retrieve(query, mode)
      writer.write({
        type: "data-sources",
        id: "retrieved-sources",
        data: { mode, store: retrieval.store, sources: retrieval.sources },
      })
      writer.write({
        type: "data-status",
        id: "status",
        transient: true,
        data: {
          stage: "answering",
          label: `Reading ${retrieval.chunks.length} source${retrieval.chunks.length === 1 ? "" : "s"}...`,
          mode,
          store: retrieval.store,
        },
      })

      for (const source of retrieval.sources) {
        if (!source.source_url) continue
        writer.write({
          type: "source-url",
          sourceId: source.chunk_id,
          url: source.source_url,
          title: source.title,
        })
      }

      const context = buildAnswerContext(retrieval.chunks, mode)
      const history = messages.slice(-4).map((message) => ({
        role: message.role,
        parts: message.parts,
        metadata: message.metadata,
      }))
      const result = streamText({
        model: openai(modelForMode(mode)),
        system: `${SYSTEM_PROMPT}

Context:
${context || "No matching context was retrieved."}`,
        messages: await convertToModelMessages(history),
        maxOutputTokens: mode === "deep" ? 1400 : 750,
        providerOptions: {
          openai: {
            reasoningEffort: mode === "deep" ? "medium" : "none",
            textVerbosity: mode === "deep" ? "medium" : "low",
            serviceTier: "auto",
          },
        },
      })

      writer.merge(result.toUIMessageStream<ResearchUIMessage>({ sendSources: false }))
    },
    onError(error) {
      return error instanceof Error ? error.message : "The chat stream failed."
    },
  })

  return createUIMessageStreamResponse({ stream })
}
