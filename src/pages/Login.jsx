import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, Lock, User, Eye, EyeOff, Cpu, Wifi, Activity } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

// Animated floating particle
function Particle({ style }) {
  return (
    <div
      className="absolute w-1 h-1 rounded-full bg-cyber-cyan/30 animate-pulse-slow"
      style={style}
    />
  )
}

function TerminalLine({ text, delay = 0, color = 'text-cyber-muted' }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])
  return visible ? (
    <p className={`font-mono text-xs ${color}`}>
      <span className="text-cyber-cyan mr-2">›</span>{text}
    </p>
  ) : null
}

const PARTICLES = Array.from({ length: 30 }, (_, i) => ({
  top:  `${Math.random() * 100}%`,
  left: `${Math.random() * 100}%`,
  animationDelay: `${Math.random() * 3}s`,
  animationDuration: `${2 + Math.random() * 3}s`,
}))

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass]  = useState(false)
  const [error, setError]        = useState('')
  const [loading, setLoading]    = useState(false)
  const [bootDone, setBootDone]  = useState(false)
  const { login } = useAuth()
  const navigate  = useNavigate()

  useEffect(() => {
    const t = setTimeout(() => setBootDone(true), 2000)
    return () => clearTimeout(t)
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    await new Promise(r => setTimeout(r, 1200)) // simulate auth
    const ok = login(username, password)
    setLoading(false)
    if (ok) {
      navigate('/')
    } else {
      setError('Invalid credentials. Access denied.')
    }
  }

  return (
    <div className="min-h-screen cyber-grid-bg flex items-center justify-center relative overflow-hidden">
      {/* Scan line */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyber-cyan/40 to-transparent animate-scan-line" />
      </div>

      {/* Particles */}
      {PARTICLES.map((s, i) => <Particle key={i} style={s} />)}

      {/* Corner decorations */}
      <div className="absolute top-0 left-0 w-32 h-32 border-l-2 border-t-2 border-cyber-cyan/20" />
      <div className="absolute top-0 right-0 w-32 h-32 border-r-2 border-t-2 border-cyber-cyan/20" />
      <div className="absolute bottom-0 left-0 w-32 h-32 border-l-2 border-b-2 border-cyber-cyan/20" />
      <div className="absolute bottom-0 right-0 w-32 h-32 border-r-2 border-b-2 border-cyber-cyan/20" />

      {/* Status bar */}
      <div className="absolute top-4 right-6 flex items-center gap-4 font-mono text-xs text-cyber-muted">
        <span className="flex items-center gap-1.5">
          <Wifi className="w-3 h-3 text-cyber-green" />
          <span className="text-cyber-green">SECURE</span>
        </span>
        <span className="flex items-center gap-1.5">
          <Activity className="w-3 h-3 text-cyber-cyan" />
          TLS 1.3
        </span>
        <span>{new Date().toLocaleTimeString()}</span>
      </div>

      {/* Boot overlay */}
      {!bootDone && (
        <div className="absolute inset-0 bg-cyber-bg z-50 flex items-center justify-center">
          <div className="space-y-2 w-72">
            <TerminalLine text="Initializing secure shell..." delay={0}    color="text-cyber-cyan" />
            <TerminalLine text="Loading encryption modules..." delay={400} />
            <TerminalLine text="Connecting to trust network..." delay={800} />
            <TerminalLine text="System ready." delay={1400} color="text-cyber-green" />
          </div>
        </div>
      )}

      {/* Login card */}
      <div className="w-full max-w-sm mx-4 animate-fade-in">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <div className="relative animate-float">
              <div className="w-20 h-20 rounded-2xl bg-cyber-cyan/10 border-2 border-cyber-cyan/40 flex items-center justify-center animate-glow-cyan">
                <Shield className="w-10 h-10 text-cyber-cyan" />
              </div>
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-cyber-green rounded-full border-2 border-cyber-bg animate-pulse" />
            </div>
          </div>
          <h1 className="font-mono text-xl font-bold text-cyber-cyan text-glow-cyan tracking-widest">
            DEEPFAKE TRUST
          </h1>
          <p className="font-mono text-xs text-cyber-muted tracking-widest mt-1">
            ATTRIBUTION SYSTEM v3.2 — RESTRICTED ACCESS
          </p>
        </div>

        {/* Card */}
        <div className="cyber-card border border-cyber-border animate-glow-cyan">
          <div className="flex items-center gap-2 mb-6">
            <Cpu className="w-4 h-4 text-cyber-cyan" />
            <p className="font-mono text-xs text-cyber-muted tracking-widest">ACCESS CONTROL TERMINAL</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Username */}
            <div className="space-y-1.5">
              <label className="font-mono text-xs text-cyber-muted tracking-widest">IDENTIFIER</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cyber-muted" />
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="analyst@dts.gov"
                  className="cyber-input pl-10"
                  autoComplete="username"
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="font-mono text-xs text-cyber-muted tracking-widest">PASSPHRASE</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cyber-muted" />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="cyber-input pl-10 pr-10"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-cyber-muted hover:text-cyber-cyan transition-colors"
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="bg-cyber-red/10 border border-cyber-red/30 rounded px-3 py-2">
                <p className="font-mono text-xs text-cyber-red">⚠ {error}</p>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="cyber-btn-primary w-full mt-2 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-cyber-cyan/30 border-t-cyber-cyan rounded-full animate-spin" />
                  AUTHENTICATING...
                </>
              ) : (
                <>
                  <Shield className="w-4 h-4" />
                  AUTHENTICATE
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-cyber-border/50">
            <p className="font-mono text-[10px] text-cyber-muted text-center">
              DEMO: enter any username + password to access
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center font-mono text-[10px] text-cyber-muted/50 mt-6">
          All access is monitored and logged — Unauthorized use is prohibited
        </p>
      </div>
    </div>
  )
}
