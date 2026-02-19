'use client'
import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, CheckCircle, XCircle, FileText } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe, uploadDocument, listDocuments, deleteDocument, getDocumentStatus, type Document } from '@/lib/api'
import styles from './upload.module.css'

const ALLOWED = [
  '.pdf', '.txt', '.md',
  '.docx', '.dotx', '.doc',
  '.pptx', '.ppt',
  '.xlsx', '.xls',
  '.odt', '.ods', '.odp',
  '.html', '.htm',
  '.csv', '.epub',
  '.asciidoc', '.adoc',
]

// Étapes du pipeline avec leurs paliers de progression
const STEPS = [
  { min: 0,  max: 10,  label: '📄 Réception du fichier…' },
  { min: 10, max: 40,  label: '🔍 Conversion Docling (OCR, tableaux…)' },
  { min: 40, max: 60,  label: '🖼️ Extraction des images…' },
  { min: 60, max: 85,  label: '🧠 Calcul des embeddings…' },
  { min: 85, max: 99,  label: '📦 Indexation dans Qdrant…' },
  { min: 99, max: 100, label: '✅ Terminé !' },
]

function getStepLabel(progress: number): string {
  const step = STEPS.find(s => progress >= s.min && progress < s.max)
  return step?.label ?? '✅ Terminé !'
}

export default function UploadPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [dragging, setDragging] = useState(false)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)
  // Map docId → progression locale (pour les docs qu'on vient d'uploader)
  const [liveProgress, setLiveProgress] = useState<Record<string, { progress: number; detail: string }>>({})

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
    setLoadingDocs(false)
  }

  // Poll le statut d'un document toutes les 2s et met à jour liveProgress
  async function pollProgress(docId: string) {
    const maxPolls = 150
    let polls = 0

    const interval = setInterval(async () => {
      polls++
      try {
        const doc = await getDocumentStatus(docId)
        const progress = doc.progress ?? 0
        const detail = doc.status_detail || getStepLabel(progress)

        setLiveProgress(prev => ({
          ...prev,
          [docId]: { progress, detail },
        }))

        if (doc.status === 'ready' || doc.status === 'error') {
          clearInterval(interval)
          // Garde le statut final 2s puis retire de liveProgress
          setTimeout(() => {
            setLiveProgress(prev => {
              const next = { ...prev }
              delete next[docId]
              return next
            })
          }, 2000)
          loadDocs()
        }
      } catch {}

      if (polls >= maxPolls) {
        clearInterval(interval)
        setLiveProgress(prev => ({
          ...prev,
          [docId]: { progress: 0, detail: '⚠️ Timeout — vérifiez les logs' },
        }))
      }
    }, 2000)
  }

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files)
    const valid = arr.filter(f => ALLOWED.some(ext => f.name.toLowerCase().endsWith(ext)))
    if (!valid.length) {
      alert(`Formats acceptés :\n${ALLOWED.join(', ')}`)
      return
    }

    for (const file of valid) {
      try {
        const doc = await uploadDocument(file)
        // Démarre le poll dès que le document est créé en DB
        setLiveProgress(prev => ({
          ...prev,
          [doc.id]: { progress: 0, detail: '📄 Réception du fichier…' },
        }))
        loadDocs()
        pollProgress(doc.id)
      } catch (err: any) {
        alert(`Erreur upload "${file.name}" : ${err.message}`)
      }
    }
  }, [])

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  async function handleDelete(id: string) {
    if (!confirm('Supprimer ce document et ses vecteurs ?')) return
    setDeleting(id)
    try {
      await deleteDocument(id)
      setDocuments(prev => prev.filter(d => d.id !== id))
      setLiveProgress(prev => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    } catch (err: any) {
      alert(err.message)
    }
    setDeleting(null)
  }

  return (
    <div className={styles.layout}>
      <Sidebar username={user?.username} />
      <main className={styles.main}>
        <div className={styles.header}>
          <h1>Upload de documents</h1>
          <p>PDF, Word, PowerPoint, Excel, ODT, HTML, CSV, EPUB, Markdown… — Max 50 MB</p>
          <p style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)' }}>
            Ces documents sont indexés dans la base vectorielle partagée — accessibles par tous les utilisateurs.
          </p>
        </div>

        {/* Zone de drop */}
        <div
          className={`${styles.dropzone} ${dragging ? styles.dragging : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => document.getElementById('fileInput')?.click()}
        >
          <Upload size={40} strokeWidth={1} />
          <p>Glissez vos fichiers ici ou <span className={styles.browse}>parcourir</span></p>
          <input
            id="fileInput"
            type="file"
            multiple
            accept={ALLOWED.join(',')}
            style={{ display: 'none' }}
            onChange={e => e.target.files && handleFiles(e.target.files)}
          />
        </div>

        {/* Liste des documents */}
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>
            Base vectorielle partagée — {documents.length} document{documents.length !== 1 ? 's' : ''}
          </h2>

          {loadingDocs && documents.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center' }}><span className="spinner" /></div>
          ) : documents.length === 0 ? (
            <p className={styles.emptyDocs}>Aucun document indexé.</p>
          ) : (
            <div className={styles.uploadList}>
              {documents.map(doc => {
                const live = liveProgress[doc.id]
                const isProcessing = doc.status === 'processing' || !!live
                const progress = live?.progress ?? doc.progress ?? 0
                const stepLabel = live?.detail ?? doc.status_detail ?? getStepLabel(progress)

                return (
                  <div key={doc.id} className={`${styles.uploadItem} ${isProcessing ? styles.uploadItemProcessing : ''}`}>
                    <FileText size={16} className={styles.fileIcon} />

                    <div className={styles.fileInfo}>
                      {/* Nom + statut sur la même ligne */}
                      <div className={styles.fileRow}>
                        <span className={styles.fileName}>{doc.original_name}</span>
                        <span className={styles.fileMeta}>
                          {doc.file_type.toUpperCase()} · {new Date(doc.created_at).toLocaleDateString('fr-FR')}
                        </span>
                      </div>

                      {/* Message d'état */}
                      <span className={`${styles.fileMessage} ${doc.status === 'error' ? styles.fileMessageError : ''}`}>
                        {doc.status === 'ready' && !live && `✅ ${doc.chunk_count} chunks indexés`}
                        {doc.status === 'error' && !live && `❌ ${doc.error_message || 'Erreur lors du traitement'}`}
                        {isProcessing && stepLabel}
                      </span>

                      {/* Barre de progression — visible uniquement pendant le traitement */}
                      {isProcessing && (
                        <div className={styles.progressWrapper}>
                          <div className={styles.progressBar}>
                            <div
                              className={styles.progressFill}
                              style={{ width: `${progress}%` }}
                            />
                          </div>
                          <span className={styles.progressPercent}>{progress}%</span>
                        </div>
                      )}
                    </div>

                    {/* Icône statut */}
                    <div className={styles.fileStatus}>
                      {isProcessing && <span className="spinner" style={{ width: 18, height: 18 }} />}
                      {doc.status === 'ready' && !live && <CheckCircle size={18} color="var(--success)" />}
                      {doc.status === 'error' && !live && <XCircle size={18} color="var(--error)" />}
                    </div>

                    {/* Bouton suppression — désactivé pendant le traitement */}
                    <button
                      className="danger"
                      onClick={() => handleDelete(doc.id)}
                      disabled={deleting === doc.id || isProcessing}
                      style={{ padding: '6px 10px', fontSize: 12, flexShrink: 0 }}
                    >
                      {deleting === doc.id
                        ? <span className="spinner" style={{ width: 14, height: 14 }} />
                        : '🗑'
                      }
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
