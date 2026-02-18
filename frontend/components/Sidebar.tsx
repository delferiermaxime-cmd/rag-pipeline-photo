'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { MessageSquare, Upload, FileText, LogOut, Settings } from 'lucide-react'
import styles from './Sidebar.module.css'

const nav = [
  { href: '/chat', icon: MessageSquare, label: 'Chat' },
  { href: '/upload', icon: Upload, label: 'Upload' },
  { href: '/documents', icon: FileText, label: 'Documents' },
]

interface Props {
  username?: string
  model?: string
  onModelChange?: (m: string) => void
  models?: string[]
}

export default function Sidebar({ username, model, onModelChange, models = [] }: Props) {
  const pathname = usePathname()
  const router = useRouter()

  function handleLogout() {
    localStorage.removeItem('token')
    router.push('/login')
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>
        <span className={styles.logoText}>RAG Local</span>
        {username && <span className={styles.username}>{username}</span>}
      </div>

      <nav className={styles.nav}>
        {nav.map(({ href, icon: Icon, label }) => (
          <Link
            key={href}
            href={href}
            className={`${styles.navItem} ${pathname === href ? styles.active : ''}`}
          >
            <Icon size={16} />
            <span>{label}</span>
          </Link>
        ))}
      </nav>

      {models.length > 0 && (
        <div className={styles.modelSection}>
          <p className={styles.sectionLabel}>Modèle LLM</p>
          <select
            value={model}
            onChange={e => onModelChange?.(e.target.value)}
            className={styles.modelSelect}
          >
            {models.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          {model && <p className={styles.modelActive}>● {model.split(':')[0]}</p>}
        </div>
      )}

      <button onClick={handleLogout} className={`ghost ${styles.logout}`}>
        <LogOut size={14} />
        <span>Déconnexion</span>
      </button>
    </aside>
  )
}
