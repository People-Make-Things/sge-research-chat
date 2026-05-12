import type { UIMessage } from "ai"
import type { ChatMode, ResearchSource } from "./rag"

export type ResearchStatus = {
  stage: "idle" | "retrieving" | "answering" | "done"
  label: string
  mode?: ChatMode
  store?: string
}

export type ResearchDataParts = {
  status: ResearchStatus
  sources: {
    mode: ChatMode
    store: string
    sources: ResearchSource[]
  }
}

export type ResearchUIMessage = UIMessage<unknown, ResearchDataParts>
