'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Trash2, FileText, AlertCircle, CheckCircle, Clock, Search } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe, listDocuments, deleteDocument, type Document } from '@/lib/api'
import styles from './documents.module.css'

export default function DocumentsPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [deletingAll, setDeletingAll] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
    loadDocs()
    const interval = setInterval(loadDocs, 5000)
    return () => clearInterval(interval)
  }, [router])

  async function loadDocs() {
    try {
      const docs = await listDocuments()
      setDocuments(docs)
    } catch {}
    setLoading(false)
  }

  async function handleDelete(id: string) {
    if (!confirm('Supprimer ce document et ses vecteurs ?')) return
    setDeleting(id)
    try {
      await deleteDocument(id)
      setDocuments(prev => prev.filter(d => d.id !== id))
    } catch (err: any) {
      alert(err.message)
    }
    setDeleting(null)
  }

  async function handleDeleteAll() {
    if (!confirm(`Supprimer TOUS les ${documents.length} documents et leurs vecteurs ? Cette action est irréversible.`)) return
    setDeletingAll(true)
    try {
      const res = await fetch('/api/v1/documents/all', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      })
      if (!res.ok) throw new Error('Erreur suppression')
      setDocuments([])
    } catch (err: any) {
      alert(err.message)
    }
    setDeletingAll(false)
  }

  const filtered = documents.filter(d =>
    d.original_name.toLowerCase().includes(search.toLowerCase())
  )

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'ready') return <CheckCircle size={14} color="var(--success)" />
    if (status === 'error') return <AlertCircle size={14} color="var(--error)" />
    return <Clock size={14} color="var(--text-muted)" />
  }

  return (
    <div className={styles.layout}>
      <Sidebar username={user?.username} />

      <main className={styles.main}>
        <div className={styles.header}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h1>Mes documents</h1>
              <p>{documents.length} document{documents.length !== 1 ? 's' : ''}</p>
            </div>
            {documents.length > 0 && (
              <button
                className="danger"
                onClick={handleDeleteAll}
                disabled={deletingAll}
                style={{ fontSize: 12, padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                {deletingAll
                  ? <span className="spinner" style={{ width: 14, height: 14 }} />
                  : <><Trash2 size={13} /> Tout supprimer</>
                }
              </button>
            )}
          </div>

          {/* Barre de recherche */}
          {documents.length > 0 && (
            <div style={{ position: 'relative', marginTop: 16 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
              <input
                type="text"
                placeholder="Rechercher un document…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: '100%', maxWidth: 500, paddingLeft: 32, paddingRight: 12,
                  height: 36, fontSize: 13, background: 'var(--bg-2)',
                  border: '1px solid var(--border)', borderRadius: 8,
                  color: 'var(--text)', boxSizing: 'border-box'
                }}
              />
            </div>
          )}
        </div>

        {loading ? (
          <div className={styles.loading}><span className="spinner" /></div>
        ) : documents.length === 0 ? (
          <div className={styles.empty}>
            <FileText size={40} strokeWidth={1} />
            <p>Aucun document. <a href="/upload">Uploader</a></p>
          </div>
        ) : filtered.length === 0 ? (
          <div className={styles.empty}>
            <p style={{ fontSize: 14 }}>Aucun document correspondant à &quot;{search}&quot;</p>
          </div>
        ) : (
          <div className={styles.list}>
            {filtered.map(doc => (
              <div key={doc.id} className={styles.item}>
                <div className={styles.itemIcon}>
                  <FileText size={16} />
                </div>
                <div className={styles.itemInfo}>
                  <span className={styles.itemName}>{doc.original_name}</span>
                  <div className={styles.itemMeta}>
                    <StatusIcon status={doc.status} />
                    <span className={styles[`status_${doc.status}`]}>
                      {doc.status === 'ready' ? `${doc.chunk_count} chunks` :
                       doc.status === 'error' ? doc.error_message || 'Erreur' :
                       'Traitement...'}
                    </span>
                    <span className={styles.dot}>·</span>
                    <span>{doc.file_type}</span>
                    <span className={styles.dot}>·</span>
                    <span>{new Date(doc.created_at).toLocaleDateString('fr-FR')}</span>
                  </div>
                </div>
                <button
                  className="danger"
                  onClick={() => handleDelete(doc.id)}
                  disabled={deleting === doc.id || deletingAll}
                  style={{ padding: '6px 12px', fontSize: 12 }}
                >
                  {deleting === doc.id ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Trash2 size={14} />}
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
