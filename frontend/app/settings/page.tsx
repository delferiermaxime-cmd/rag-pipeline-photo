'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Save, RotateCcw } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe } from '@/lib/api'
import styles from './settings.module.css'

const DEFAULTS = {
  temperature: 0.1,
  topK: 5,
  maxTokens: 1024,
  systemPrompt: `Tu es un assistant qui répond aux questions à partir des documents fournis. Si la réponse n'est pas dans le contexte, dis "Information non trouvée dans les documents fournis."\n\nSois précis et concis.`,
}

export default function SettingsPage() {
  const router = useRouter()
  const [user, setUser] = useState<any>(null)
  const [s, setS] = useState(DEFAULTS)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getMe().then(setUser).catch(() => router.push('/login'))
    try {
      const raw = localStorage.getItem('rag_settings')
      if (raw) setS({ ...DEFAULTS, ...JSON.parse(raw) })
    } catch {}
  }, [router])

  function handleSave() {
    localStorage.setItem('rag_settings', JSON.stringify(s))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  function handleReset() {
    setS(DEFAULTS)
    localStorage.setItem('rag_settings', JSON.stringify(DEFAULTS))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className={styles.layout}>
      <Sidebar username={user?.username} />
      <main className={styles.main}>
        <div className={styles.header}>
          <h1>Paramètres</h1>
          <p>Configuration du LLM et de la recherche vectorielle</p>
        </div>

        <div className={styles.sections}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Prompt système</h2>
            <p className={styles.sectionDesc}>Instructions données au LLM avant chaque réponse.</p>
            <textarea className={styles.textarea} value={s.systemPrompt}
              onChange={e => setS(prev => ({ ...prev, systemPrompt: e.target.value }))} rows={6} />
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Paramètres LLM</h2>

            <div className={styles.field}>
              <label className={styles.label}>Température <span className={styles.value}>{s.temperature}</span></label>
              <p className={styles.fieldDesc}>0 = réponses déterministes · 1 = plus créatif</p>
              <input type="range" min={0} max={1} step={0.05} value={s.temperature} className={styles.range}
                onChange={e => setS(prev => ({ ...prev, temperature: parseFloat(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>0</span><span>1</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>Tokens max <span className={styles.value}>{s.maxTokens}</span></label>
              <p className={styles.fieldDesc}>Longueur maximale de la réponse du LLM</p>
              <input type="range" min={256} max={4096} step={128} value={s.maxTokens} className={styles.range}
                onChange={e => setS(prev => ({ ...prev, maxTokens: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>256</span><span>4096</span></div>
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Paramètres RAG</h2>

            <div className={styles.field}>
              <label className={styles.label}>Chunks récupérés (TOP_K) <span className={styles.value}>{s.topK}</span></label>
              <p className={styles.fieldDesc}>Nombre de passages extraits de la base vectorielle par question</p>
              <input type="range" min={1} max={20} step={1} value={s.topK} className={styles.range}
                onChange={e => setS(prev => ({ ...prev, topK: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>1</span><span>20</span></div>
            </div>
          </div>

          <div className={styles.actions}>
            <button onClick={handleReset} className="ghost" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <RotateCcw size={14} /> Réinitialiser
            </button>
            <button onClick={handleSave} className="primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Save size={14} /> {saved ? '✓ Sauvegardé !' : 'Sauvegarder'}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
