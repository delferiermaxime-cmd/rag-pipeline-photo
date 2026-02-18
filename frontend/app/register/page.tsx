'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { register } from '@/lib/api'
import styles from '../login/auth.module.css'

export default function RegisterPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    // Validation côté client
    if (!email || !email.includes('@')) {
      setError("Adresse email invalide.")
      return
    }
    if (username.length < 3) {
      setError("Le nom d'utilisateur doit faire au moins 3 caractères.")
      return
    }
    if (password.length < 8) {
      setError("Le mot de passe doit faire au moins 8 caractères.")
      return
    }

    setLoading(true)
    try {
      await register(email, username, password)
      router.push('/login')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>RAG Local</h1>
        <p className={styles.subtitle}>Créer un compte</p>

        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <div className={styles.field}>
            <label>Email</label>
            <input
              type="text"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div className={styles.field}>
            <label>Nom d'utilisateur</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="username"
              autoComplete="username"
            />
          </div>
          <div className={styles.field}>
            <label>Mot de passe</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="new-password"
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <button type="submit" className="primary" disabled={loading} style={{ width: '100%' }}>
            {loading ? <span className="spinner" /> : "Créer le compte"}
          </button>
        </form>

        <p className={styles.link}>
          Déjà un compte ? <a href="/login">Se connecter</a>
        </p>
      </div>
    </div>
  )
}
