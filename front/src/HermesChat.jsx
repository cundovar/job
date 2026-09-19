import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import './HermesChat.css'

const SESSION_KEY = 'hermes_chat_session'

// Panneau de chat flottant vers l'agent Hermes (proxy /api/hermes/*, clé côté serveur uniquement).
function HermesChat() {
  const [open, setOpen] = useState(false)
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState(null)
  const historyLoadedRef = useRef(false)
  const listRef = useRef(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, open])

  useEffect(() => {
    if (!open || historyLoadedRef.current || !sessionId) return
    historyLoadedRef.current = true
    setLoadingHistory(true)
    fetch(`/api/hermes/messages/${encodeURIComponent(sessionId)}`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data.messages)) setMessages(data.messages)
      })
      .catch(() => setError("Impossible de charger l'historique de la conversation."))
      .finally(() => setLoadingHistory(false))
  }, [open, sessionId])

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
              <div key={i} className={`hermes-msg hermes-msg--${msg.role}`}>
                {msg.content}
              </div>
            ))}
            {sending && <div className="hermes-msg hermes-msg--assistant hermes-thinking">Réflexion…</div>}
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
