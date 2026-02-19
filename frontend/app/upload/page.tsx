'use client'
import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, CheckCircle, XCircle, FileText, Clock } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe, uploadDocument, listDocuments, deleteDocument, getDocumentStatus, type Document } from '@/lib/api'
import styles from './upload.module.css'

interface UploadState {
  file: File
  status: 'pending' | 'uploading' | 'indexing' | 'done' | 'error'
  uploadProgress: number   // progression de l'upload HTTP (0-100)
  docProgress: number      // progression du pipeline Docling (0-100)
  message?: string
  docId?: string
}

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

export default function UploadPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [uploads, setUploads] = useState<UploadState[]>([])
  const [dragging, setDragging] = useState(false)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
    loadDocs()
    // Rafraîchissement auto toutes les 4s pour mettre à jour les statuts
    const interval = setInterval(loadDocs, 4000)
    return () => clearInterval(interval)
  }, [router])

  async function loadDocs() {
    try {
      const docs = await listDocuments()
      setDocuments(docs)
    } catch {}
    setLoadingDocs(false)
  }

  // FIX progression : poll le statut d'un document en cours d'indexation
  async function pollDocumentProgress(docId: string, fileRef: File) {
    const maxPolls = 150   // max 5 minutes (150 × 2s)
    let polls = 0

    const interval = setInterval(async () => {
      polls++
      try {
        const doc = await getDocumentStatus(docId)

        setUploads(prev => prev.map(u =>
          u.docId === docId
            ? {
                ...u,
                docProgress: doc.progress ?? 0,
                message: doc.status_detail || 'Traitement en cours…',
              }
            : u
        ))

        if (doc.status === 'ready') {
          clearInterval(interval)
          setUploads(prev => prev.map(u =>
            u.docId === docId
              ? { ...u, status: 'done', docProgress: 100, message: doc.status_detail || `${doc.chunk_count} chunks indexés` }
              : u
          ))
          loadDocs()
        } else if (doc.status === 'error') {
          clearInterval(interval)
          setUploads(prev => prev.map(u =>
            u.docId === docId
              ? { ...u, status: 'error', docProgress: 0, message: doc.error_message || 'Erreur lors du traitement' }
              : u
          ))
          loadDocs()
        }
      } catch {}

      if (polls >= maxPolls) {
        clearInterval(interval)
        setUploads(prev => prev.map(u =>
          u.docId === docId
            ? { ...u, status: 'error', message: 'Timeout : traitement trop long' }
            : u
        ))
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

    const newUploads: UploadState[] = valid.map(f => ({
      file: f,
      status: 'pending',
      uploadProgress: 0,
      docProgress: 0,
    }))
    setUploads(prev => [...prev, ...newUploads])

    for (const file of valid) {
      // Phase 1 : upload HTTP
      setUploads(prev => prev.map(u =>
        u.file === file ? { ...u, status: 'uploading', uploadProgress: 10, message: 'Upload en cours…' } : u
      ))

      // Progression de l'upload simulée (pas d'XHR progress ici)
      const uploadTimer = setInterval(() => {
        setUploads(prev => prev.map(u =>
          u.file === file && u.status === 'uploading' && u.uploadProgress < 90
            ? { ...u, uploadProgress: u.uploadProgress + 10 }
            : u
        ))
      }, 200)

      try {
        const doc = await uploadDocument(file)
        clearInterval(uploadTimer)

        // Phase 2 : pipeline Docling (indexation en background)
        setUploads(prev => prev.map(u =>
          u.file === file
            ? { ...u, status: 'indexing', uploadProgress: 100, docProgress: 0, message: 'Conversion du document…', docId: doc.id }
            : u
        ))

        // FIX : on poll le vrai statut depuis le backend
        pollDocumentProgress(doc.id, file)
        loadDocs()

      } catch (err: any) {
        clearInterval(uploadTimer)
        setUploads(prev => prev.map(u =>
          u.file === file
            ? { ...u, status: 'error', uploadProgress: 0, docProgress: 0, message: err.message }
            : u
        ))
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
    } catch (err: any) {
      alert(err.message)
    }
    setDeleting(null)
  }

  const statusLabel = (doc: Document) => {
    if (doc.status === 'ready') return `✅ ${doc.chunk_count} chunks indexés`
    if (doc.status === 'error') return `❌ ${doc.error_message || 'Erreur'}`
    return `⏳ ${doc.status_detail || 'Indexation en cours…'}`
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

        {/* Uploads en cours */}
        {uploads.length > 0 && (
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>En cours de traitement</h2>
            <div className={styles.uploadList}>
              {uploads.map((u, i) => (
                <div key={i} className={styles.uploadItem}>
                  <FileText size={16} className={styles.fileIcon} />
                  <div className={styles.fileInfo}>
                    <span className={styles.fileName}>{u.file.name}</span>

                    {/* Phase upload */}
                    {u.status === 'uploading' && (
                      <>
                        <span className={styles.fileMessage}>Upload… {u.uploadProgress}%</span>
                        <div className={styles.progressBar}>
                          <div className={styles.progressFill} style={{ width: `${u.uploadProgress}%` }} />
                        </div>
                      </>
                    )}

                    {/* FIX phase indexation : barre de progression réelle depuis le backend */}
                    {u.status === 'indexing' && (
                      <>
                        <span className={styles.fileMessage}>{u.message || 'Traitement…'}</span>
                        <div className={styles.progressBar}>
                          <div
                            className={`${styles.progressFill} ${styles.progressIndexing}`}
                            style={{ width: `${u.docProgress}%` }}
                          />
                        </div>
                        <span className={styles.progressPercent}>{u.docProgress}%</span>
                      </>
                    )}

                    {(u.status === 'done' || u.status === 'error') && (
                      <span className={styles.fileMessage}>{u.message}</span>
                    )}
                  </div>
                  <div className={styles.fileStatus}>
                    {(u.status === 'uploading' || u.status === 'indexing') && (
                      <span className="spinner" style={{ width: 18, height: 18 }} />
                    )}
                    {u.status === 'done' && <CheckCircle size={18} color="var(--success)" />}
                    {u.status === 'error' && <XCircle size={18} color="var(--error)" />}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Documents indexés */}
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>
            Base vectorielle partagée — {documents.length} document{documents.length !== 1 ? 's' : ''}
          </h2>
          {loadingDocs ? (
            <div style={{ padding: 20, textAlign: 'center' }}><span className="spinner" /></div>
          ) : documents.length === 0 ? (
            <p className={styles.emptyDocs}>Aucun document indexé.</p>
          ) : (
            <div className={styles.uploadList}>
              {documents.map(doc => (
                <div key={doc.id} className={styles.uploadItem}>
                  <FileText size={16} className={styles.fileIcon} />
                  <div className={styles.fileInfo}>
                    <span className={styles.fileName}>{doc.original_name}</span>
                    <span className={styles.fileMessage}>
                      {statusLabel(doc)} · {doc.file_type.toUpperCase()} · {new Date(doc.created_at).toLocaleDateString('fr-FR')}
                    </span>
                    {/* Barre de progression pour les docs en cours dans la liste globale */}
                    {doc.status === 'processing' && (
                      <div className={styles.progressBar}>
                        <div
                          className={`${styles.progressFill} ${styles.progressIndexing}`}
                          style={{ width: `${doc.progress ?? 0}%` }}
                        />
                      </div>
                    )}
                  </div>
                  <button
                    className="danger"
                    onClick={() => handleDelete(doc.id)}
                    disabled={deleting === doc.id || doc.status === 'processing'}
                    style={{ padding: '6px 10px', fontSize: 12 }}
                  >
                    {deleting === doc.id ? <span className="spinner" style={{ width: 14, height: 14 }} /> : '🗑'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
