"use client"

import { useMemo, useState } from "react"
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useAssistantRuntime,
  type DataMessagePartProps,
  type TextMessagePartProps,
} from "@assistant-ui/react"
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/react-ai-sdk"
import { ArrowDown, ArrowUp, Plus, Sparkles, Square } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import type { ChatMode, ResearchSource } from "@/lib/rag"
import type { ResearchStatus, ResearchUIMessage } from "@/lib/chat-types"

const starterPrompts = [
  "What TikTok hooks are working for consumer apps this month?",
  "Find faceless formats that study apps can adapt.",
  "Compare the strongest dating app creator playbooks.",
  "What should a new habit app copy from recent SGE examples?",
]

export function ResearchChat() {
  const [mode, setMode] = useState<ChatMode>("fast")
  const [status, setStatus] = useState<ResearchStatus>({
    stage: "idle",
    label: "Ready",
    mode: "fast",
  })
  const transport = useMemo(
    () =>
      new AssistantChatTransport<ResearchUIMessage>({
        api: "/api/chat",
        prepareSendMessagesRequest({ messages, body }) {
          return {
            body: {
              ...body,
              messages,
              mode,
            },
          }
        },
      }),
    [mode],
  )

  const runtime = useChatRuntime<ResearchUIMessage>({
    transport,
    onData(part) {
      if (part.type === "data-status") setStatus(part.data)
      if (part.type === "data-sources") {
        setStatus({
          stage: "answering",
          label: `${part.data.sources.length} sources`,
          mode: part.data.mode,
          store: part.data.store,
        })
      }
    },
    onFinish() {
      setStatus((current) => ({
        ...current,
        stage: "done",
        label: current.store ? `Ready · ${current.store}` : "Ready",
      }))
    },
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ResearchShell mode={mode} setMode={setMode} status={status} />
    </AssistantRuntimeProvider>
  )
}

function ResearchShell({
  mode,
  setMode,
  status,
}: {
  mode: ChatMode
  setMode: (mode: ChatMode) => void
  status: ResearchStatus
}) {
  const runtime = useAssistantRuntime()

  return (
    <main className="research-shell">
      <section className="chat-workspace" aria-label="Research chat">
        <header className="chat-header">
          <div className="brand-row">
          <button
              className="icon-button"
            type="button"
            onClick={() => void runtime.threads.switchToNewThread()}
            aria-label="New chat"
            title="New chat"
          >
              <Plus size={17} />
          </button>
            <div>
              <p className="eyebrow">SGE Research</p>
              <h1>Ask the archive.</h1>
            </div>
          </div>
          <div className="header-controls">
            <div className="live-status" aria-live="polite">
              <span className={`status-light status-${status.stage}`} />
              <span>{status.label}</span>
            </div>
            <ModeToggle mode={mode} setMode={setMode} />
          </div>
        </header>

        <Thread />
      </section>
    </main>
  )
}

function ModeToggle({ mode, setMode }: { mode: ChatMode; setMode: (mode: ChatMode) => void }) {
  return (
    <div className="mode-toggle" role="group" aria-label="Answer mode">
      <button type="button" className={mode === "fast" ? "active" : ""} onClick={() => setMode("fast")}>
        Fast
      </button>
      <button type="button" className={mode === "deep" ? "active" : ""} onClick={() => setMode("deep")}>
        Deep
      </button>
    </div>
  )
}

function Thread() {
  return (
    <ThreadPrimitive.Root className="thread-root">
      <ThreadPrimitive.Viewport className="thread-viewport">
        <div className="message-stack">
          <ThreadPrimitive.Empty>
            <EmptyState />
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages components={{ Message: ThreadMessageView }} />
        </div>

        <ThreadPrimitive.ViewportFooter className="thread-footer">
          <ThreadPrimitive.ScrollToBottom className="scroll-button">
            <ArrowDown size={16} />
          </ThreadPrimitive.ScrollToBottom>
          <Composer />
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  )
}

function EmptyState() {
  return (
    <div className="empty-state">
      <h2>What should we find?</h2>
      <div className="prompt-grid" aria-label="Starter prompts">
        {starterPrompts.map((prompt) => (
          <ThreadPrimitive.Suggestion key={prompt} prompt={prompt} send className="prompt-chip">
            {prompt}
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
    </div>
  )
}

function ThreadMessageView() {
  const role = useAuiState((state) => state.message.role)

  return (
    <MessagePrimitive.Root className={`message-row message-row-${role}`}>
      <div className="message-label">{role === "user" ? "You" : "SGE"}</div>
      <div className="message-body">
        <MessagePrimitive.Parts
          components={{
            Text: MarkdownPart,
            Empty: RunningPart,
            data: {
              by_name: {
                sources: SourcesDrawerPart,
                status: StatusPart,
              },
            },
          }}
        />
        <MessagePrimitive.Error>
          <ErrorPrimitive.Root className="message-error">
            <ErrorPrimitive.Message />
          </ErrorPrimitive.Root>
        </MessagePrimitive.Error>
      </div>
    </MessagePrimitive.Root>
  )
}

function MarkdownPart({ text }: TextMessagePartProps) {
  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}

function SourcesDrawerPart({ data }: DataMessagePartProps<{ sources: ResearchSource[]; mode: ChatMode; store: string }>) {
  const sources: ResearchSource[] = Array.isArray(data.sources) ? data.sources : []
  if (!sources.length) return null

  return (
    <details className="source-drawer">
      <summary>
        <Sparkles size={14} />
        <span>{sources.length} sources</span>
        <small>{data.store}</small>
      </summary>
      <div className="source-list">
        {sources.map((source, index) => (
          <a key={source.chunk_id || source.source_url} href={source.source_url} target="_blank" rel="noreferrer">
            <span>{index + 1}</span>
            <strong>{source.title}</strong>
            {source.published_at ? <small>{source.published_at.slice(0, 10)}</small> : null}
          </a>
        ))}
      </div>
    </details>
  )
}

function StatusPart() {
  return null
}

function RunningPart() {
  return (
    <div className="typing-indicator" aria-label="Searching and answering">
      <span />
      <span />
      <span />
    </div>
  )
}

function Composer() {
  const isRunning = useAuiState((state) => state.thread.isRunning)
  const buttonLabel = useMemo(() => (isRunning ? "Stop" : "Send"), [isRunning])

  return (
    <ComposerPrimitive.Root className="composer-root">
      <ComposerPrimitive.Input
        className="composer-input"
        placeholder="Ask about hooks, formats, creators, niches..."
        rows={1}
        autoFocus
        aria-label="Message"
      />
      <div className="composer-actions">
        {isRunning ? (
          <ComposerPrimitive.Cancel className="send-button" aria-label="Stop answer">
            <Square size={15} />
            <span>{buttonLabel}</span>
          </ComposerPrimitive.Cancel>
        ) : (
          <ComposerPrimitive.Send className="send-button" aria-label="Send message">
            <ArrowUp size={17} />
            <span>{buttonLabel}</span>
          </ComposerPrimitive.Send>
        )}
      </div>
    </ComposerPrimitive.Root>
  )
}
