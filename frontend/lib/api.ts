const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('token')
}

async function apiFetch(path: string, options: RequestInit = {}) {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}/api/v1${path}`, { ...options, headers })
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  return res
}

function extractErrorMessage(detail: any, fallback: string): string {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ')
  return fallback
}

export async function login(username: string, password: string) {
  const res = await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  if (!res.ok) { const err = await res.json(); throw new Error(extractErrorMessage(err.detail, 'Erreur de connexion')) }
  const data = await res.json()
  localStorage.setItem('token', data.access_token)
  return data
}

export async function register(email: string, username: string, password: string) {
  const res = await apiFetch('/auth/register', { method: 'POST', body: JSON.stringify({ email, username, password }) })
  if (!res.ok) { const err = await res.json(); throw new Error(extractErrorMessage(err.detail, 'Erreur inscription')) }
  return res.json()
}

export async function getMe() {
  const res = await apiFetch('/auth/me')
  if (!res.ok) throw new Error('Not authenticated')
  return res.json()
}

export async function uploadDocument(file: File) {
  const token = getToken()
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/api/v1/documents/upload`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
  })
  if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur upload') }
  return res.json()
}

export async function listDocuments() {
  const res = await apiFetch('/documents/')
  if (!res.ok) throw new Error('Erreur chargement documents')
  return res.json()
}

export async function deleteDocument(id: string) {
  const res = await apiFetch(`/documents/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Erreur suppression')
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await apiFetch('/chat/conversations')
  if (!res.ok) throw new Error('Erreur chargement conversations')
  return res.json()
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await apiFetch(`/chat/conversations/${id}`)
  if (!res.ok) throw new Error('Erreur chargement conversation')
  return res.json()
}

export async function deleteConversation(id: string) {
  const res = await apiFetch(`/chat/conversations/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Erreur suppression conversation')
}

export async function getModels() {
  const res = await apiFetch('/chat/models')
  if (!res.ok) throw new Error('Erreur chargement modèles')
  return res.json()
}

export function streamChat(
  question: string,
  model: string,
  onToken: (token: string) => void,
  onSources: (sources: Source[]) => void,
  onDone: () => void,
  onError: (err: string) => void,
  onConversationId: (id: string) => void,
  conversationId?: string,
  settings?: { temperature?: number; topK?: number; maxTokens?: number },
): () => void {
  const token = getToken()
  const controller = new AbortController()

  fetch(`${API_BASE}/api/v1/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      question,
      model,
      conversation_id: conversationId || null,
      temperature: settings?.temperature,
      top_k: settings?.topK,
      max_tokens: settings?.maxTokens,
    }),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) { onError('Erreur serveur'); return }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'conversation_id') onConversationId(data.conversation_id)
            else if (data.type === 'token') onToken(data.token)
            else if (data.type === 'sources') onSources(data.sources)
            else if (data.type === 'done') onDone()
            else if (data.type === 'error') onError(data.error)
          } catch {}
        }
      }
    }
  }).catch((err) => { if (err.name !== 'AbortError') onError(err.message) })

  return () => controller.abort()
}

export interface Source { document_id: string; title: string; page: number | null; content: string; score: number }
export interface Document { id: string; original_name: string; file_type: string; status: string; chunk_count: number; created_at: string; error_message?: string }
export interface Conversation { id: string; title: string; created_at: string; updated_at: string }
export interface ConversationDetail extends Conversation {
  messages: { id: string; role: string; content: string; created_at: string }[]
}
