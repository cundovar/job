import { useEffect, useRef, useState } from 'react'
import { Send, Search } from 'lucide-react'
import './HermesChat.css'

const SESSION_KEY = 'hermes_chat_session'
const SEARCH_POLL_MS = 5000

// Panneau de chat flottant vers l'agent Hermes (proxy /api/hermes/*, clé côté serveur uniquement).
// `onSearchDone(searchId)` : appelé quand une recherche lancée depuis le chat se termine, pour
// que App.jsx rafraîchisse la liste des sessions. `onOpenSearch(searchId)` : appelé quand
// l'utilisateur clique sur le lien « voir la recherche » dans le fil.
function HermesChat({ onSearchDone, onOpenSearch }) {
  const [open, setOpen] = useState(false)
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState(null)
  const [searchRun, setSearchRun] = useState(null) // { runId, searchId, status: 'running'|'done'|'failed' }
  const historyLoadedRef = useRef(false)
  const listRef = useRef(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, open])

  useEffect(() => {
    if (!open || historyLoadedRef.current || !sessionId) return
    setLoadingHistory(true)
    fetch(`/api/hermes/messages/${encodeURIComponent(sessionId)}`)
      .then(res => res.json())
      .then(data => {
        // Marqué "chargé" seulement en cas de succès : si la requête échoue, on
        // retente au prochain réaffichage du panneau plutôt que de rester bloqué.
        historyLoadedRef.current = true
        if (Array.isArray(data.messages)) setMessages(data.messages)
      })
      .catch(() => setError("Impossible de charger l'historique de la conversation."))
      .finally(() => setLoadingHistory(false))
  }, [open, sessionId])

  // Sonde /api/hermes/search/:runId tant qu'une recherche lancée depuis le chat tourne.
  useEffect(() => {
    if (!searchRun || searchRun.status !== 'running') return
    let cancelled = false

    const poll = async () => {
      try {
        const res = await fetch(`/api/hermes/search/${encodeURIComponent(searchRun.runId)}`)
        const data = await res.json()
        if (cancelled) return
        if (!res.ok) throw new Error(data?.error || `Erreur ${res.status}`)
        if (data.status === 'running') return

        if (data.status === 'done') {
          setMessages(current => [
            ...current,
            { role: 'assistant', content: data.output || 'Recherche terminée.' },
            { role: 'assistant', content: '__search-link__', searchId: searchRun.searchId },
          ])
          onSearchDone?.(searchRun.searchId)
        } else {
          setMessages(current => [
            ...current,
            { role: 'assistant', content: `La recherche a échoué : ${data.error || 'erreur inconnue'}` },
          ])
        }
        setSearchRun(current => (current?.runId === searchRun.runId ? { ...current, status: data.status } : current))
      } catch {
        // Erreur réseau transitoire : on continue de sonder au tour suivant.
      }
    }

    const timer = setInterval(poll, SEARCH_POLL_MS)
    return () => { cancelled = true; clearInterval(timer) }
  }, [searchRun, onSearchDone])

  async function sendMessage() {
    const message = input.trim()
    if (!message || sending) return
    setInput('')
    setError(null)
    setMessages(current => [...current, { role: 'user', content: message }])
    setSending(true)
    try {
      const res = await fetch('/api/hermes/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, message }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.error || `Erreur ${res.status}`)
      if (data.sessionId && data.sessionId !== sessionId) {
        setSessionId(data.sessionId)
        localStorage.setItem(SESSION_KEY, data.sessionId)
      }
      setMessages(current => [...current, { role: 'assistant', content: data.content }])
    } catch (err) {
      setError(err.message || "L'agent Hermes n'a pas répondu.")
    } finally {
      setSending(false)
    }
  }

  const searchRunning = searchRun?.status === 'running'

  // Lance une recherche d'emploi via Hermes (route /api/hermes/search, tâche longue) au lieu
  // d'un échange de chat classique — déclenché uniquement par le bouton « Rechercher ».
  async function sendSearchMessage() {
    const message = input.trim()
    if (!message || sending || searchRunning) return
    setInput('')
    setError(null)
    setMessages(current => [...current, { role: 'user', content: message }])
    setSending(true)
    try {
      const res = await fetch('/api/hermes/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, message }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.error || `Erreur ${res.status}`)
      setMessages(current => [
        ...current,
        { role: 'assistant', content: "C'est lancé, je te préviens quand c'est fini." },
      ])
      setSearchRun({ runId: data.runId, searchId: data.searchId, status: 'running' })
    } catch (err) {
      setError(err.message || "Impossible de lancer la recherche.")
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function newConversation() {
    localStorage.removeItem(SESSION_KEY)
    historyLoadedRef.current = true
    setSessionId(null)
    setMessages([])
    setError(null)
    setInput('')
  }

  return (
    <>
      <button
        className="hermes-fab"
        onClick={() => setOpen(o => !o)}
        aria-label={open ? 'Fermer le chat Hermes' : 'Ouvrir le chat Hermes'}
      >
        💬 Hermes
      </button>

      {open && (
        <div className="hermes-panel">
          <div className="hermes-panel-header">
            <span>💬 Hermes</span>
            <button className="hermes-icon-btn" onClick={newConversation} title="Nouvelle conversation">
              🗑 Nouvelle conversation
            </button>
          </div>

          <div className="hermes-messages" ref={listRef}>
            {loadingHistory && <p className="hermes-hint">Chargement de l'historique…</p>}
            {!loadingHistory && messages.length === 0 && (
              <p className="hermes-hint">Écris un message pour démarrer la conversation avec Hermes.</p>
            )}
            {messages.map((msg, i) => (
              msg.content === '__search-link__' ? (
                <div key={i} className="hermes-msg hermes-msg--assistant">
                  Le résultat détaillé est dans la liste des sessions, pas ici.
                  {onOpenSearch && (
                    <button
                      type="button"
                      className="hermes-search-link"
                      onClick={() => onOpenSearch(msg.searchId)}
                    >
                      🔎 Voir la recherche
                    </button>
                  )}
                </div>
              ) : (
                <div key={i} className={`hermes-msg hermes-msg--${msg.role}`}>
                  {msg.content}
                </div>
              )
            ))}
            {sending && <div className="hermes-msg hermes-msg--assistant hermes-thinking">Réflexion…</div>}
            {searchRunning && (
              <div className="hermes-msg hermes-msg--assistant hermes-thinking">Recherche en cours…</div>
            )}
          </div>

          {error && <div className="hermes-error">{error}</div>}

          <div className="hermes-input-row">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Écrire à Hermes… (Entrée pour envoyer, Maj+Entrée pour une nouvelle ligne)"
              disabled={sending}
            />
            <button
              className="btn hermes-search-btn"
              onClick={sendSearchMessage}
              disabled={sending || searchRunning || !input.trim()}
              title="Lancer une recherche d'emploi avec cette demande"
            >
              <Search />
            </button>
            <button className="btn btn--primary" onClick={sendMessage} disabled={sending || !input.trim()}>
              <Send />
            </button>
          </div>
        </div>
      )}
    </>
  )
}

export default HermesChat
