'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Trash2, FileText, AlertCircle, CheckCircle, Clock } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe, listDocuments, deleteDocument, type Document } from '@/lib/api'
import styles from './documents.module.css'

export default function DocumentsPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
    loadDocs()
    const interval = setInterval(loadDocs, 5000) // Poll for status updates
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
          <h1>Mes documents</h1>
          <p>{documents.length} document{documents.length !== 1 ? 's' : ''}</p>
        </div>

        {loading ? (
          <div className={styles.loading}><span className="spinner" /></div>
        ) : documents.length === 0 ? (
          <div className={styles.empty}>
            <FileText size={40} strokeWidth={1} />
            <p>Aucun document. <a href="/upload">Uploader</a></p>
          </div>
        ) : (
          <div className={styles.list}>
            {documents.map(doc => (
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
                  disabled={deleting === doc.id}
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
