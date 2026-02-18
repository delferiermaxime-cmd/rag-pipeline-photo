'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Send, Paperclip, X, Trash2, Plus, ChevronLeft } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import {
  getMe, getModels, streamChat, listConversations, getConversation, deleteConversation,
  type Source, type Conversation
} from '@/lib/api'
import styles from './chat.module.css'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

// Parse un fichier texte/pdf côté client (upload temporaire dans la conversation)
async function parseFileLocally(file: File): Promise<string> {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''

  if (['txt', 'md', 'csv', 'html', 'htm'].includes(ext)) {
    return await file.text()
  }

  if (ext === 'pdf') {
    // Lire le PDF avec pdf.js si disponible, sinon envoyer le texte brut
    try {
      const arrayBuffer = await file.arrayBuffer()
      // Extraction basique du texte PDF sans librairie
      const bytes = new Uint8Array(arrayBuffer)
      const text = new TextDecoder('latin1').decode(bytes)
      // Extraction des chaînes lisibles
      const readable = text.match(/[^\x00-\x08\x0E-\x1F\x7F-\xFF]{4,}/g) || []
      return readable.join(' ').replace(/\s+/g, ' ').trim()
    } catch {
      return `[Contenu de ${file.name} - format PDF non prévisualisable]`
    }
  }

  return `[Fichier: ${file.name} - ${(file.size / 1024).toFixed(1)} KB]`
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
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConvId, setActiveConvId] = useState<string | undefined>(undefined)
  const [showHistory, setShowHistory] = useState(false)
  // Fichier temporaire pour la conversation (pas dans la base vectorielle)
  const [inlineFile, setInlineFile] = useState<{ name: string; content: string } | null>(null)
  const [loadingFile, setLoadingFile] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<(() => void) | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
    getModels().then(data => {
      setModels(data.models)
      setModel(data.default || data.models[0])
    }).catch(() => {})
    loadConversations()
  }, [router])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadConversations() {
    try {
      const convs = await listConversations()
      setConversations(convs)
    } catch {}
  }

  async function loadConversation(id: string) {
    try {
      const conv = await getConversation(id)
      setMessages(conv.messages.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })))
      setActiveConvId(id)
      setShowHistory(false)
      setInlineFile(null)
    } catch {}
  }

  function newConversation() {
    setMessages([])
    setActiveConvId(undefined)
    setInlineFile(null)
    setShowHistory(false)
  }

  async function handleDeleteConv(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    await deleteConversation(id)
    if (activeConvId === id) newConversation()
    loadConversations()
  }

  // Upload temporaire — parse le fichier localement, pas dans Qdrant
  async function handleInlineFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setLoadingFile(true)
    try {
      const content = await parseFileLocally(file)
      setInlineFile({ name: file.name, content })
    } catch {
      alert("Impossible de lire le fichier")
    } finally {
      setLoadingFile(false)
      e.target.value = ''
    }
  }

  function handleSend() {
    if (!input.trim() || streaming) return
    const question = input.trim()
    setInput('')

    // Si un fichier inline est présent, l'injecter dans la question
    const fullQuestion = inlineFile
      ? `[Document: ${inlineFile.name}]\n${inlineFile.content.slice(0, 8000)}\n\n---\n${question}`
      : question

    const userMsg: Message = { role: 'user', content: question }
    const assistantMsg: Message = { role: 'assistant', content: '' }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    cancelRef.current = streamChat(
      fullQuestion,
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
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { ...updated[updated.length - 1], sources: s }
          return updated
        })
      },
      () => {
        setStreaming(false)
        loadConversations()
      },
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
      (id) => setActiveConvId(id),
      activeConvId,
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

      {/* Panneau historique */}
      {showHistory && (
        <div className={styles.historyPanel}>
          <div className={styles.historyHeader}>
            <span>Historique</span>
            <button onClick={() => setShowHistory(false)} className="ghost" style={{ padding: 4 }}>
              <X size={16} />
            </button>
          </div>
          <button onClick={newConversation} className={`primary ${styles.newConvBtn}`}>
            <Plus size={14} /> Nouvelle conversation
          </button>
          <div className={styles.convList}>
            {conversations.length === 0 && <p className={styles.emptyHistory}>Aucun historique</p>}
            {conversations.map(conv => (
              <div
                key={conv.id}
                className={`${styles.convItem} ${conv.id === activeConvId ? styles.activeConv : ''}`}
                onClick={() => loadConversation(conv.id)}
              >
                <span className={styles.convTitle}>{conv.title}</span>
                <button
                  className="ghost"
                  onClick={(e) => handleDeleteConv(conv.id, e)}
                  style={{ padding: 2, opacity: 0.5 }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <main className={styles.main}>
        {/* Barre outils */}
        <div className={styles.toolbar}>
          <button
            className={`ghost ${styles.historyBtn}`}
            onClick={() => setShowHistory(!showHistory)}
            title="Historique des conversations"
          >
            <ChevronLeft size={16} style={{ transform: showHistory ? 'rotate(180deg)' : 'none' }} />
            Historique
          </button>
          <button className="ghost" onClick={newConversation} title="Nouvelle conversation">
            <Plus size={16} /> Nouvelle
          </button>
        </div>

        <div className={styles.messages}>
          {messages.length === 0 && (
            <div className={styles.empty}>
              <p>Posez une question sur vos documents</p>
              <p style={{ fontSize: 13, opacity: 0.5, marginTop: 8 }}>
                Utilisez 📎 pour joindre un fichier temporaire à la conversation
              </p>
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

        {/* Fichier inline attaché */}
        {inlineFile && (
          <div className={styles.inlineFile}>
            <Paperclip size={12} />
            <span>{inlineFile.name}</span>
            <span style={{ opacity: 0.5, fontSize: 11 }}>(temporaire — non indexé)</span>
            <button onClick={() => setInlineFile(null)} className="ghost" style={{ padding: 2 }}>
              <X size={12} />
            </button>
          </div>
        )}

        <div className={styles.inputArea}>
          <div className={styles.inputWrapper}>
            {/* Bouton upload temporaire */}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="ghost"
              title="Joindre un fichier à cette conversation (non indexé)"
              disabled={loadingFile || streaming}
              style={{ padding: '6px 8px' }}
            >
              {loadingFile ? <span className="spinner" style={{ width: 16, height: 16 }} /> : <Paperclip size={16} />}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: 'none' }}
              accept=".txt,.md,.csv,.html,.htm,.pdf"
              onChange={handleInlineFile}
            />

            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Posez une question… (Entrée pour envoyer)"
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
