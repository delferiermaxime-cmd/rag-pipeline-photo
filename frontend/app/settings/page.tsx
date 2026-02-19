'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Save, RotateCcw } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe } from '@/lib/api'
import styles from './settings.module.css'

const DEFAULT_PROMPT = ``

const DEFAULTS = {
  temperature: 0.1,
  topK: 5,
  maxTokens: 1024,
  minScore: 0.0,
  contextMaxChars: 12000,
  systemPrompt: DEFAULT_PROMPT,
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
            <textarea
              className={styles.textarea}
              value={s.systemPrompt}
              onChange={e => setS(prev => ({ ...prev, systemPrompt: e.target.value }))}
              rows={6}
            />
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Paramètres LLM</h2>

            <div className={styles.field}>
              <label className={styles.label}>
                Température <span className={styles.value}>{s.temperature}</span>
              </label>
              <p className={styles.fieldDesc}>0 = réponses déterministes · 1 = plus créatif</p>
              <input type="range" min={0} max={1} step={0.05} value={s.temperature}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, temperature: parseFloat(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>0</span><span>1</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>
                Tokens max <span className={styles.value}>{s.maxTokens}</span>
              </label>
              <p className={styles.fieldDesc}>Longueur maximale de la réponse du LLM</p>
              <input type="range" min={256} max={4096} step={128} value={s.maxTokens}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, maxTokens: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>256</span><span>4096</span></div>
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Paramètres RAG</h2>

            <div className={styles.field}>
              <label className={styles.label}>
                Chunks récupérés (TOP_K) <span className={styles.value}>{s.topK}</span>
              </label>
              <p className={styles.fieldDesc}>Nombre de passages extraits de la base vectorielle par question</p>
              <input type="range" min={1} max={20} step={1} value={s.topK}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, topK: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>1</span><span>20</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>
                Score de similarité minimum <span className={styles.value}>{s.minScore}</span>
              </label>
              <p className={styles.fieldDesc}>Seuil en dessous duquel les chunks sont ignorés (0 = tout accepter)</p>
              <input type="range" min={0} max={1} step={0.05} value={s.minScore}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, minScore: parseFloat(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>0</span><span>1</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>
                Contexte max (caractères) <span className={styles.value}>{s.contextMaxChars.toLocaleString()}</span>
              </label>
              <p className={styles.fieldDesc}>Taille maximale du contexte envoyé au LLM</p>
              <input type="range" min={2000} max={32000} step={1000} value={s.contextMaxChars}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, contextMaxChars: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>2k</span><span>32k</span></div>
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
