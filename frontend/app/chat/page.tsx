'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Send } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe, getModels, streamChat, type Source } from '@/lib/api'
import styles from './chat.module.css'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

export default function ChatPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [showSources, setShowSources] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
    getModels().then(data => {
      setModels(data.models)
      setModel(data.default || data.models[0])
    }).catch(() => {})
  }, [router])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    if (!input.trim() || streaming) return
    const question = input.trim()
    setInput('')

    const userMsg: Message = { role: 'user', content: question }
    const assistantMsg: Message = { role: 'assistant', content: '' }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    let sources: Source[] = []

    cancelRef.current = streamChat(
      question,
      model,
      (token) => {
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: updated[updated.length - 1].content + token,
          }
          return updated
        })
      },
      (s) => {
        sources = s
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { ...updated[updated.length - 1], sources: s }
          return updated
        })
      },
      () => setStreaming(false),
      (err) => {
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: `Erreur: ${err}`,
          }
          return updated
        })
        setStreaming(false)
      },
    )
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className={styles.layout}>
      <Sidebar username={user?.username} model={model} onModelChange={setModel} models={models} />

      <main className={styles.main}>
        <div className={styles.messages}>
          {messages.length === 0 && (
            <div className={styles.empty}>
              <p>Posez une question sur vos documents</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`${styles.message} ${styles[msg.role]}`}>
              <div className={styles.bubble}>
                {msg.content || (msg.role === 'assistant' && streaming && i === messages.length - 1 ? (
                  <div className="dot-pulse"><span /><span /><span /></div>
                ) : null)}
                {msg.role === 'assistant' && msg.content && (
                  <div className={styles.cursor}>{streaming && i === messages.length - 1 ? '▋' : ''}</div>
                )}
              </div>

              {msg.sources && msg.sources.length > 0 && (
                <div className={styles.sourcesWrapper}>
                  <button
                    className={styles.sourcesToggle}
                    onClick={() => setShowSources(showSources === i ? null : i)}
                  >
                    {showSources === i ? '▾' : '▸'} {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                  </button>

                  {showSources === i && (
                    <div className={styles.sources}>
                      {msg.sources.map((s, j) => (
                        <div key={j} className={styles.source}>
                          <div className={styles.sourceHeader}>
                            <span className={styles.sourceTitle}>{s.title}</span>
                            {s.page && <span className={styles.sourcePage}>p.{s.page}</span>}
                            <span className={styles.sourceScore}>{(s.score * 100).toFixed(0)}%</span>
                          </div>
                          <p className={styles.sourceContent}>{s.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <div className={styles.inputArea}>
          <div className={styles.inputWrapper}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Posez une question... (Entrée pour envoyer)"
              rows={1}
              className={styles.input}
              disabled={streaming}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              className={`primary ${styles.sendBtn}`}
            >
              {streaming ? <span className="spinner" style={{ width: 16, height: 16 }} /> : <Send size={16} />}
            </button>
          </div>
          <p className={styles.hint}>Modèle actif: <strong>{model}</strong></p>
        </div>
      </main>
    </div>
  )
}
