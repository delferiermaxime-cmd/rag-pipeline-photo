'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Save, RotateCcw } from 'lucide-react'
import Sidebar from '@/components/Sidebar'
import { getMe } from '@/lib/api'
import styles from './settings.module.css'

const DEFAULT_PROMPT = `Tu es un assistant intelligent. Tu as acces a des documents fournis dans le contexte.\n\nRegles :\n1. Si la reponse est dans les documents fournis, reponds en te basant sur eux et cite les sources.\n2. Si la reponse n'est pas dans les documents mais que tu la connais, reponds normalement.\n3. Sois precis et concis.`

const DEFAULTS = {
  temperature: 0.1,
  topK: 5,
  maxTokens: 1024,
  minScore: 0.3,
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
          <h1>Param&egrave;tres</h1>
          <p>Configuration du LLM et de la recherche vectorielle</p>
        </div>

        <div className={styles.sections}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Prompt syst&egrave;me</h2>
            <p className={styles.sectionDesc}>Instructions donn&eacute;es au LLM avant chaque r&eacute;ponse.</p>
            <textarea
              className={styles.textarea}
              value={s.systemPrompt}
              onChange={e => setS(prev => ({ ...prev, systemPrompt: e.target.value }))}
              rows={6}
            />
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Param&egrave;tres LLM</h2>

            <div className={styles.field}>
              <label className={styles.label}>
                Temp&eacute;rature <span className={styles.value}>{s.temperature}</span>
              </label>
              <p className={styles.fieldDesc}>0 = r&eacute;ponses d&eacute;terministes &middot; 1 = plus cr&eacute;atif</p>
              <input type="range" min={0} max={1} step={0.05} value={s.temperature}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, temperature: parseFloat(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>0</span><span>1</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>
                Tokens max <span className={styles.value}>{s.maxTokens}</span>
              </label>
              <p className={styles.fieldDesc}>Longueur maximale de la r&eacute;ponse du LLM</p>
              <input type="range" min={256} max={4096} step={128} value={s.maxTokens}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, maxTokens: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>256</span><span>4096</span></div>
            </div>
          </div>

          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>Param&egrave;tres RAG</h2>

            <div className={styles.field}>
              <label className={styles.label}>
                Chunks r&eacute;cup&eacute;r&eacute;s (TOP_K) <span className={styles.value}>{s.topK}</span>
              </label>
              <p className={styles.fieldDesc}>Nombre de passages extraits de la base vectorielle par question</p>
              <input type="range" min={1} max={20} step={1} value={s.topK}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, topK: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>1</span><span>20</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>
                Score de similarit&eacute; minimum <span className={styles.value}>{s.minScore}</span>
              </label>
              <p className={styles.fieldDesc}>Seuil en dessous duquel les chunks sont ignor&eacute;s (0 = tout accepter)</p>
              <input type="range" min={0} max={1} step={0.05} value={s.minScore}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, minScore: parseFloat(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>0</span><span>1</span></div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>
                Contexte max (caract&egrave;res) <span className={styles.value}>{s.contextMaxChars.toLocaleString()}</span>
              </label>
              <p className={styles.fieldDesc}>Taille maximale du contexte envoy&eacute; au LLM</p>
              <input type="range" min={2000} max={32000} step={1000} value={s.contextMaxChars}
                className={styles.range}
                onChange={e => setS(prev => ({ ...prev, contextMaxChars: parseInt(e.target.value) }))} />
              <div className={styles.rangeLabels}><span>2k</span><span>32k</span></div>
            </div>
          </div>

          <div className={styles.actions}>
            <button onClick={handleReset} className="ghost" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <RotateCcw size={14} /> R&eacute;initialiser
            </button>
            <button onClick={handleSave} className="primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Save size={14} /> {saved ? '\u2713 Sauvegardd !' : 'Sauvegarder'}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
