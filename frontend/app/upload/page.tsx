'use client'
import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, CheckCircle, XCircle, FileText } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe, uploadDocument } from '@/lib/api'
import styles from './upload.module.css'

interface UploadState {
  file: File
  status: 'pending' | 'uploading' | 'done' | 'error'
  message?: string
}

// Synchronisé avec ALLOWED_EXTENSIONS du backend (config.py)
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

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
  }, [router])

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files)
    const valid = arr.filter(f => ALLOWED.some(ext => f.name.toLowerCase().endsWith(ext)))
    if (!valid.length) {
      alert(`Formats acceptés :\n${ALLOWED.join(', ')}`)
      return
    }
    setUploads(prev => [...prev, ...valid.map(f => ({ file: f, status: 'pending' as const }))])
    for (const file of valid) {
      setUploads(prev => prev.map(u => u.file === file ? { ...u, status: 'uploading' } : u))
      try {
        await uploadDocument(file)
        setUploads(prev => prev.map(u => u.file === file
          ? { ...u, status: 'done', message: 'En cours de traitement…' } : u))
      } catch (err: any) {
        setUploads(prev => prev.map(u => u.file === file
          ? { ...u, status: 'error', message: err.message } : u))
      }
    }
  }, [])

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div className={styles.layout}>
      <Sidebar username={user?.username} />
      <main className={styles.main}>
        <div className={styles.header}>
          <h1>Upload de documents</h1>
          <p>PDF, Word, PowerPoint, Excel, ODT, HTML, CSV, EPUB, Markdown… — Max 50 MB</p>
        </div>

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

        {uploads.length > 0 && (
          <div className={styles.uploadList}>
            {uploads.map((u, i) => (
              <div key={i} className={styles.uploadItem}>
                <FileText size={16} className={styles.fileIcon} />
                <div className={styles.fileInfo}>
                  <span className={styles.fileName}>{u.file.name}</span>
                  {u.message && <span className={styles.fileMessage}>{u.message}</span>}
                </div>
                <div className={styles.fileStatus}>
                  {u.status === 'uploading' && <span className="spinner" style={{ width: 18, height: 18 }} />}
                  {u.status === 'done' && <CheckCircle size={18} color="var(--success)" />}
                  {u.status === 'error' && <XCircle size={18} color="var(--error)" />}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
