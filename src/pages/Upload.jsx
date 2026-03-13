import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Upload as UploadIcon, X, Film, Image, Music,
  Shield, AlertTriangle, CheckCircle, Sliders, Zap,
  Wifi, WifiOff,
} from 'lucide-react'
import Sidebar from '../components/Sidebar'
import { analyzeFile, checkBackendHealth } from '../utils/api'

const ACCEPTED = {
  'video/*': ['.mp4', '.mov', '.avi', '.webm', '.mkv'],
  'audio/*': ['.mp3', '.wav', '.aac', '.flac', '.ogg'],
  'image/*': ['.jpg', '.jpeg', '.png'],
}
const ALL_EXT = Object.values(ACCEPTED).flat()

function fileIcon(type) {
  if (!type) return UploadIcon
  if (type.startsWith('video')) return Film
  if (type.startsWith('audio')) return Music
  return Image
}

function formatBytes(b) {
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / (1024 * 1024)).toFixed(2) + ' MB'
}

const ANALYSIS_STEPS = [
  'Hashing file contents...',
  'Parsing file metadata...',
  'Running forensic analysis...',
  'Detecting facial patterns...',
  'Checking noise consistency...',
  'Analysing compression artefacts...',
  'Computing trust score...',
  'Building attribution record...',
]

export default function Upload() {
  const navigate = useNavigate()
  const inputRef  = useRef(null)
  const [file, setFile]               = useState(null)
  const [dragging, setDragging]       = useState(false)
  const [error, setError]             = useState('')
  const [analyzing, setAnalyzing]     = useState(false)
  const [progress, setProgress]       = useState(0)
  const [step, setStep]               = useState('')
  const [sensitivity, setSensitivity] = useState('MEDIUM')
  const [checks, setChecks] = useState({
    facial: true, audio: true, metadata: true, frequency: true,
  })
  const [backendOk, setBackendOk] = useState(null)   // null=checking, true, false

  // Check backend health on mount
  useEffect(() => {
    checkBackendHealth().then(ok => setBackendOk(ok))
  }, [])

  const acceptFile = useCallback((f) => {
    if (!f) return
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    if (!ALL_EXT.includes(ext)) {
      setError(`Unsupported format: ${ext}`)
      return
    }
    if (f.size > 500 * 1024 * 1024) {
      setError('File too large. Maximum 500 MB.')
      return
    }
    setError('')
    setFile(f)
  }, [])

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    acceptFile(e.dataTransfer.files[0])
  }

  async function handleAnalyze() {
    if (!file) return
    setAnalyzing(true)
    setProgress(0)
    setError('')

    // ── Step animation runs independently of the real API call ──────────────
    // It advances every ~2 s and stops at 88 % so the final "100 %" belongs
    // to the actual server response, giving truthful feedback.
    let stopped = false
    let stepIdx = 0

    ;(async () => {
      while (stepIdx < ANALYSIS_STEPS.length - 1 && !stopped) {
        setStep(ANALYSIS_STEPS[stepIdx])
        setProgress(Math.round(((stepIdx + 1) / (ANALYSIS_STEPS.length)) * 88))
        stepIdx++
        await new Promise(r => setTimeout(r, 1800 + Math.random() * 1400))
      }
    })()

    // ── Real backend call ─────────────────────────────────────────────────
    try {
      const result = await analyzeFile(file, { sensitivity, checks })
      stopped = true
      setStep('Analysis complete.')
      setProgress(100)
      await new Promise(r => setTimeout(r, 450))
      navigate('/results', { state: { result } })
    } catch (err) {
      stopped = true
      setAnalyzing(false)
      setProgress(0)
      setStep('')
      setError(err.message || 'Analysis failed — check that the backend is running.')
    }
  }

  const FileIcon = fileIcon(file?.type)

  return (
    <div className="flex h-screen bg-cyber-bg overflow-hidden">
      <Sidebar />

      <main className="flex-1 overflow-y-auto">
        {/* Topbar */}
        <header className="sticky top-0 z-10 bg-cyber-panel/90 backdrop-blur border-b border-cyber-border px-6 py-3">
          <h1 className="font-mono text-lg font-bold text-cyber-cyan text-glow-cyan">MEDIA INGESTION</h1>
          <p className="font-mono text-xs text-cyber-muted">Upload media for deepfake detection & attribution</p>
        </header>

        <div className="p-6 max-w-4xl mx-auto space-y-6">

          {/* Backend status banner */}
          {backendOk === false && (
            <div className="bg-cyber-red/10 border border-cyber-red/30 rounded-lg px-4 py-3 flex items-center gap-3">
              <WifiOff className="w-4 h-4 text-cyber-red shrink-0" />
              <div className="flex-1">
                <p className="font-mono text-sm text-cyber-red font-semibold">BACKEND OFFLINE</p>
                <p className="font-mono text-xs text-cyber-red/70 mt-0.5">
                  Start the Python server:&nbsp;
                  <code className="bg-cyber-red/10 px-1 rounded">cd backend &amp;&amp; uvicorn main:app --reload</code>
                </p>
              </div>
            </div>
          )}
          {backendOk === true && (
            <div className="bg-cyber-green/5 border border-cyber-green/20 rounded-lg px-4 py-2 flex items-center gap-2">
              <Wifi className="w-3.5 h-3.5 text-cyber-green" />
              <p className="font-mono text-xs text-cyber-green">Analysis backend connected — real detection active</p>
            </div>
          )}

          {/* Drop zone */}
          <div
            onClick={() => !file && inputRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`
              relative border-2 border-dashed rounded-xl p-12 text-center cursor-pointer
              transition-all duration-300
              ${dragging
                ? 'border-cyber-cyan bg-cyber-cyan/5 scale-[1.01]'
                : file
                ? 'border-cyber-green/40 bg-cyber-green/5 cursor-default'
                : 'border-cyber-border/50 hover:border-cyber-cyan/40 hover:bg-cyber-cyan/5'
              }
            `}
          >
            {/* Animated corners */}
            <div className={`absolute top-2 left-2 w-6 h-6 border-l-2 border-t-2 transition-colors ${dragging ? 'border-cyber-cyan' : 'border-cyber-border'}`} />
            <div className={`absolute top-2 right-2 w-6 h-6 border-r-2 border-t-2 transition-colors ${dragging ? 'border-cyber-cyan' : 'border-cyber-border'}`} />
            <div className={`absolute bottom-2 left-2 w-6 h-6 border-l-2 border-b-2 transition-colors ${dragging ? 'border-cyber-cyan' : 'border-cyber-border'}`} />
            <div className={`absolute bottom-2 right-2 w-6 h-6 border-r-2 border-b-2 transition-colors ${dragging ? 'border-cyber-cyan' : 'border-cyber-border'}`} />

            <input
              ref={inputRef}
              type="file"
              accept={Object.keys(ACCEPTED).join(',')}
              className="hidden"
              onChange={e => acceptFile(e.target.files[0])}
            />

            {!file ? (
              <>
                <div className={`w-20 h-20 rounded-2xl mx-auto mb-5 flex items-center justify-center border-2
                  ${dragging ? 'border-cyber-cyan bg-cyber-cyan/20 animate-glow-cyan' : 'border-cyber-border bg-cyber-card'}`}>
                  <UploadIcon className={`w-9 h-9 ${dragging ? 'text-cyber-cyan' : 'text-cyber-muted'}`} />
                </div>
                <p className="font-mono text-cyber-text font-semibold mb-1">
                  {dragging ? 'DROP FILE TO UPLOAD' : 'DRAG & DROP MEDIA FILE'}
                </p>
                <p className="font-mono text-xs text-cyber-muted mb-4">or click to browse</p>
                <div className="flex flex-wrap justify-center gap-2">
                  {['MP4', 'AVI', 'MOV', 'MP3', 'WAV', 'JPG', 'JPEG', 'PNG'].map(f => (
                    <span key={f} className="badge-info">{f}</span>
                  ))}
                </div>
                <p className="font-mono text-[11px] text-cyber-muted mt-3">Max file size: 500 MB</p>
              </>
            ) : (
              <div className="flex items-center gap-6">
                <div className="w-16 h-16 rounded-xl bg-cyber-green/10 border border-cyber-green/30 flex items-center justify-center shrink-0">
                  <FileIcon className="w-8 h-8 text-cyber-green" />
                </div>
                <div className="text-left flex-1 min-w-0">
                  <p className="font-mono text-cyber-text font-semibold truncate">{file.name}</p>
                  <p className="font-mono text-xs text-cyber-muted mt-1">
                    {formatBytes(file.size)} · {file.type || 'unknown'}
                  </p>
                  <span className="badge-safe mt-2 inline-block">READY FOR ANALYSIS</span>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); setFile(null); setError('') }}
                  className="shrink-0 w-8 h-8 rounded-lg bg-cyber-red/10 border border-cyber-red/30 flex items-center justify-center text-cyber-red hover:bg-cyber-red/20 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {error && (
            <div className="bg-cyber-red/10 border border-cyber-red/30 rounded-lg px-4 py-3 flex items-center gap-3">
              <AlertTriangle className="w-4 h-4 text-cyber-red shrink-0" />
              <p className="font-mono text-sm text-cyber-red">{error}</p>
            </div>
          )}

          {/* Settings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Sensitivity */}
            <div className="cyber-card">
              <div className="flex items-center gap-2 mb-4">
                <Sliders className="w-4 h-4 text-cyber-cyan" />
                <p className="font-mono text-xs text-cyber-muted tracking-widest">DETECTION SENSITIVITY</p>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {['LOW', 'MEDIUM', 'HIGH'].map(s => (
                  <button
                    key={s}
                    onClick={() => setSensitivity(s)}
                    className={`py-2 rounded font-mono text-xs tracking-widest border transition-all
                      ${sensitivity === s
                        ? s === 'HIGH'
                          ? 'bg-cyber-red/20 border-cyber-red/50 text-cyber-red'
                          : s === 'MEDIUM'
                          ? 'bg-cyber-yellow/20 border-cyber-yellow/50 text-cyber-yellow'
                          : 'bg-cyber-green/20 border-cyber-green/50 text-cyber-green'
                        : 'bg-transparent border-cyber-border/30 text-cyber-muted hover:border-cyber-border'
                      }`}
                  >{s}</button>
                ))}
              </div>
              <p className="font-mono text-[10px] text-cyber-muted mt-3">
                {sensitivity === 'HIGH'
                  ? 'More false positives — catches subtle manipulations'
                  : sensitivity === 'MEDIUM'
                  ? 'Balanced detection — recommended for most use cases'
                  : 'Fewer false positives — only obvious manipulations flagged'}
              </p>
            </div>

            {/* Check types */}
            <div className="cyber-card">
              <div className="flex items-center gap-2 mb-4">
                <Zap className="w-4 h-4 text-cyber-cyan" />
                <p className="font-mono text-xs text-cyber-muted tracking-widest">ANALYSIS MODULES</p>
              </div>
              <div className="space-y-2.5">
                {[
                  { key: 'facial',    label: 'Facial Inconsistency' },
                  { key: 'audio',     label: 'Audio-Visual Sync' },
                  { key: 'metadata',  label: 'Metadata Integrity' },
                  { key: 'frequency', label: 'Frequency Analysis' },
                ].map(({ key, label }) => (
                  <label key={key} className="flex items-center gap-3 cursor-pointer group">
                    <button
                      type="button"
                      onClick={() => setChecks(c => ({ ...c, [key]: !c[key] }))}
                      className={`w-9 h-5 rounded-full border transition-all relative shrink-0
                        ${checks[key]
                          ? 'bg-cyber-cyan/20 border-cyber-cyan/50'
                          : 'bg-cyber-border/30 border-cyber-border/50'
                        }`}
                    >
                      <span className={`absolute top-0.5 w-4 h-4 rounded-full transition-all
                        ${checks[key]
                          ? 'left-4 bg-cyber-cyan shadow-[0_0_6px_#00d4ff]'
                          : 'left-0.5 bg-cyber-muted'
                        }`} />
                    </button>
                    <span className={`font-mono text-xs transition-colors ${checks[key] ? 'text-cyber-text' : 'text-cyber-muted'}`}>
                      {label}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* Analysis progress */}
          {analyzing && (
            <div className="cyber-card border-cyber-cyan/30 animate-glow-cyan">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-lg bg-cyber-cyan/10 border border-cyber-cyan/30 flex items-center justify-center">
                  <Shield className="w-4 h-4 text-cyber-cyan animate-pulse" />
                </div>
                <div>
                  <p className="font-mono text-sm text-cyber-cyan">ANALYSIS IN PROGRESS</p>
                  <p className="font-mono text-xs text-cyber-muted">{step}</p>
                </div>
                <span className="ml-auto font-mono text-2xl font-bold text-cyber-cyan">{progress}%</span>
              </div>

              <div className="progress-bar mb-2">
                <div
                  className="progress-fill bg-gradient-to-r from-cyber-purple via-cyber-cyan to-cyber-green"
                  style={{ width: `${progress}%` }}
                />
              </div>

              <div className="mt-4 grid grid-cols-4 gap-2">
                {ANALYSIS_STEPS.slice(0, 4).map((s, i) => (
                  <div key={i} className={`h-1 rounded-full transition-all duration-500
                    ${i <= Math.floor((progress / 100) * 4)
                      ? 'bg-cyber-cyan'
                      : 'bg-cyber-border'
                    }`} />
                ))}
              </div>
            </div>
          )}

          {/* Submit */}
          {!analyzing && (
            <button
              onClick={handleAnalyze}
              disabled={!file}
              className={`w-full cyber-btn flex items-center justify-center gap-3 py-4 text-base
                ${file ? 'cyber-btn-primary' : 'border-cyber-border/30 text-cyber-muted cursor-not-allowed'}`}
            >
              {file ? (
                <>
                  <Shield className="w-5 h-5" />
                  RUN DEEPFAKE ANALYSIS
                  <CheckCircle className="w-5 h-5" />
                </>
              ) : (
                <>
                  <UploadIcon className="w-5 h-5" />
                  UPLOAD A FILE TO BEGIN
                </>
              )}
            </button>
          )}

          {/* Info footer */}
          <div className="bg-cyber-card/50 border border-cyber-border/30 rounded-lg px-4 py-3">
            <p className="font-mono text-[11px] text-cyber-muted leading-relaxed">
              <span className="text-cyber-cyan">ℹ PRIVACY:</span> Uploaded files are processed in an isolated sandbox,
              hashed for integrity, then deleted after analysis. No original media is retained.
              All analysis metadata is logged for audit purposes per NIST SP 800-53.
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
