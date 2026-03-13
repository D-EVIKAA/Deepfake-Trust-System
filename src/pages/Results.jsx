import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts'
import {
  Shield, ShieldAlert, Download, ArrowLeft, Link2,
  Hash, Clock, FileType, CheckCircle, XCircle, AlertTriangle,
  ChevronRight, Lock, Cpu,
} from 'lucide-react'
import Sidebar     from '../components/Sidebar'
import TrustGauge  from '../components/TrustGauge'
import { downloadReport } from '../utils/api'

function CheckBar({ label, value, inverted = false }) {
  // value = anomaly score (0=clean, 100=very bad)
  const display = inverted ? value : 100 - value
  const color =
    value > 60 ? '#ff3366'
    : value > 30 ? '#ffcc00'
    : '#00ff88'

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between font-mono text-xs">
        <span className="text-cyber-muted">{label}</span>
        <span style={{ color }}>
          {value > 60 ? 'ANOMALY' : value > 30 ? 'SUSPECT' : 'NORMAL'}
          <span className="text-cyber-muted ml-1">({value}%)</span>
        </span>
      </div>
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${value}%`, background: color, boxShadow: `0 0 8px ${color}88`, transition: 'width 1.2s ease-out' }}
        />
      </div>
    </div>
  )
}

function ProvenanceNode({ label, hash, active, first, last }) {
  return (
    <div className="flex items-center gap-2">
      {!first && <ChevronRight className="w-3 h-3 text-cyber-muted shrink-0" />}
      <div className={`px-3 py-2 rounded-lg border font-mono text-xs ${active
        ? 'bg-cyber-cyan/10 border-cyber-cyan/40 text-cyber-cyan'
        : 'bg-cyber-card border-cyber-border/50 text-cyber-muted'
      }`}>
        <p className="font-semibold">{label}</p>
        <p className="text-[10px] opacity-60 mt-0.5 truncate max-w-[100px]">{hash.slice(0, 10)}…</p>
      </div>
    </div>
  )
}

export default function Results() {
  const { state } = useLocation()
  const navigate  = useNavigate()
  const [downloading, setDownloading] = useState(false)

  const result = state?.result

  async function handleDownload() {
    if (!result?.id) return
    setDownloading(true)
    try {
      await downloadReport(result.id)
    } catch (err) {
      alert(`Download failed: ${err.message}`)
    } finally {
      setDownloading(false)
    }
  }

  if (!result) {
    return (
      <div className="flex h-screen bg-cyber-bg overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="font-mono text-cyber-muted mb-4">No analysis result to display.</p>
            <button onClick={() => navigate('/upload')} className="cyber-btn-primary py-2">
              UPLOAD A FILE
            </button>
          </div>
        </main>
      </div>
    )
  }

  const {
    id, filename, trustScore, verdict, confidence,
    checks, provenance, timestamp, size, type, model,
    videoMlProbability, audioMlProbability, mlFakeProbability,
  } = result

  const hasMlData = (
    videoMlProbability !== undefined ||
    audioMlProbability !== undefined ||
    mlFakeProbability  !== undefined
  )

  // Build radar data from checks (or mock if from RECENT_ANALYSES)
  const c = checks ?? {
    facialInconsistency:  verdict === 'DEEPFAKE' ? 72 : 15,
    audioVisualSync:      verdict === 'DEEPFAKE' ? 65 : 10,
    metadataIntegrity:    verdict === 'DEEPFAKE' ? 58 : 8,
    compressionArtifacts: verdict === 'DEEPFAKE' ? 80 : 20,
    frequencyAnalysis:    verdict === 'DEEPFAKE' ? 74 : 12,
    temporalConsistency:  verdict === 'DEEPFAKE' ? 61 : 18,
  }

  const radarData = [
    { axis: 'Facial',      value: c.facialInconsistency  },
    { axis: 'Audio Sync',  value: c.audioVisualSync      },
    { axis: 'Metadata',    value: c.metadataIntegrity    },
    { axis: 'Compression', value: c.compressionArtifacts },
    { axis: 'Frequency',   value: c.frequencyAnalysis    },
    { axis: 'Temporal',    value: c.temporalConsistency  },
  ]

  const verdictColor  = verdict === 'DEEPFAKE' ? '#ff3366' : verdict === 'SUSPICIOUS' ? '#ffcc00' : '#00ff88'
  const VerdictIcon   = verdict === 'DEEPFAKE' ? ShieldAlert : verdict === 'SUSPICIOUS' ? AlertTriangle : CheckCircle
  const prov = provenance ?? {
    originalHash: '0xdeadbeef1234567890abcdef',
    firstSeen: timestamp,
    locations: ['upload-endpoint', 'analysis-cluster', 'attribution-db'],
    signatures: 2,
  }

  return (
    <div className="flex h-screen bg-cyber-bg overflow-hidden">
      <Sidebar />

      <main className="flex-1 overflow-y-auto">
        {/* Topbar */}
        <header className="sticky top-0 z-10 bg-cyber-panel/90 backdrop-blur border-b border-cyber-border px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(-1)}
              className="flex items-center gap-1.5 font-mono text-xs text-cyber-muted hover:text-cyber-cyan transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              BACK
            </button>
            <div className="w-px h-6 bg-cyber-border" />
            <div>
              <h1 className="font-mono text-lg font-bold text-cyber-cyan text-glow-cyan">ANALYSIS REPORT</h1>
              <p className="font-mono text-xs text-cyber-muted">{id} · {new Date(timestamp).toLocaleString()}</p>
            </div>
          </div>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="cyber-btn-primary flex items-center gap-2 py-2 disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            {downloading ? 'DOWNLOADING…' : 'DOWNLOAD REPORT'}
          </button>
        </header>

        <div className="p-6 space-y-6">
          {/* Verdict banner */}
          <div
            className="cyber-card flex items-center gap-4"
            style={{ borderColor: verdictColor + '44', boxShadow: `0 0 20px ${verdictColor}11` }}
          >
            <div
              className="w-14 h-14 rounded-xl flex items-center justify-center border-2 shrink-0"
              style={{ borderColor: verdictColor + '60', background: verdictColor + '15' }}
            >
              <VerdictIcon className="w-7 h-7" style={{ color: verdictColor }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="font-mono font-bold text-xl" style={{ color: verdictColor }}>
                  {verdict}
                </span>
                <span className="badge-info">ID: {id}</span>
                {confidence && <span className="badge-safe">{confidence}% CONFIDENCE</span>}
              </div>
              <p className="font-mono text-xs text-cyber-muted mt-1 truncate">{filename}</p>
            </div>
            <div className="text-right shrink-0 hidden sm:block">
              <p className="font-mono text-xs text-cyber-muted">Model</p>
              <p className="font-mono text-sm text-cyber-cyan">{model ?? 'DeepScan v3.2'}</p>
              <p className="font-mono text-xs text-cyber-muted mt-1">{type} · {size ?? 'N/A'}</p>
            </div>
          </div>

          {/* Trust gauge + radar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="cyber-card flex flex-col items-center justify-center py-8">
              <p className="font-mono text-xs text-cyber-muted tracking-widest mb-6">TRUST SCORE</p>
              <TrustGauge score={trustScore} size={220} />
            </div>

            <div className="cyber-card">
              <p className="font-mono text-xs text-cyber-muted tracking-widest mb-2">ANOMALY RADAR</p>
              <p className="font-mono text-[10px] text-cyber-muted mb-4">Higher values = more anomalous</p>
              <ResponsiveContainer width="100%" height={240}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#1a3a5c" />
                  <PolarAngleAxis
                    dataKey="axis"
                    tick={{ fontFamily: 'Fira Code', fontSize: 10, fill: '#4a6080' }}
                  />
                  <Radar
                    dataKey="value"
                    stroke={verdictColor}
                    fill={verdictColor}
                    fillOpacity={0.2}
                    strokeWidth={2}
                  />
                  <Tooltip
                    contentStyle={{ background: '#0d1f38', border: '1px solid #1a3a5c', fontFamily: 'Fira Code', fontSize: 11 }}
                    itemStyle={{ color: verdictColor }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Detection checks */}
          <div className="cyber-card">
            <p className="font-mono text-xs text-cyber-muted tracking-widest mb-6">DETECTION MODULE RESULTS</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
              <CheckBar label="Facial Inconsistency"   value={c.facialInconsistency}  />
              <CheckBar label="Audio-Visual Sync"      value={c.audioVisualSync}      />
              <CheckBar label="Metadata Integrity"     value={c.metadataIntegrity}    />
              <CheckBar label="Compression Artifacts"  value={c.compressionArtifacts} />
              <CheckBar label="Frequency Domain"       value={c.frequencyAnalysis}    />
              <CheckBar label="Temporal Consistency"   value={c.temporalConsistency}  />
            </div>
          </div>

          {/* ML Analysis Results */}
          {hasMlData && (
            <div className="cyber-card border-cyber-border/50">
              <div className="flex items-center gap-2 mb-5">
                <Cpu className="w-4 h-4 text-cyber-cyan" />
                <p className="font-mono text-xs text-cyber-muted tracking-widest">ML ANALYSIS RESULTS</p>
                <span className="ml-auto font-mono text-[10px] text-cyber-muted/60">
                  Hugging Face pretrained models
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
                {[
                  {
                    label: type === 'AUDIO' ? 'Audio AI Probability' : 'Video AI Probability',
                    value: type === 'AUDIO' ? audioMlProbability : videoMlProbability,
                    model: type === 'AUDIO'
                      ? 'm3hrdadfi/wav2vec2-xlsr-deepfake-detection'
                      : 'umm-maybe/AI-image-detector',
                  },
                  ...(type === 'VIDEO' ? [{
                    label: 'Audio AI Probability',
                    value: audioMlProbability,
                    model: 'm3hrdadfi/wav2vec2-xlsr-deepfake-detection',
                  }] : []),
                  {
                    label: 'Combined ML Score',
                    value: mlFakeProbability,
                    model: 'max(video, audio)',
                  },
                ].map(({ label, value, model: mLabel }) => {
                  const pct   = value !== undefined ? Math.round(value * 100) : null
                  const color = pct === null ? '#4a6080'
                    : pct > 70 ? '#ff3366'
                    : pct > 50 ? '#ffcc00'
                    : '#00ff88'
                  const status = pct === null ? 'N/A'
                    : pct > 70 ? 'HIGH RISK'
                    : pct > 50 ? 'SUSPECT'
                    : pct > 30 ? 'LOW RISK'
                    : 'CLEAN'

                  return (
                    <div
                      key={label}
                      className="bg-cyber-bg/50 rounded-lg p-4 border border-cyber-border/30 space-y-3"
                    >
                      <p className="font-mono text-[10px] text-cyber-muted tracking-widest">{label}</p>
                      <p className="font-mono text-3xl font-bold" style={{ color }}>
                        {pct !== null ? `${pct}%` : 'N/A'}
                      </p>
                      <p className="font-mono text-[10px]" style={{ color }}>{status}</p>
                      <div className="progress-bar">
                        <div
                          className="progress-fill"
                          style={{
                            width: `${pct ?? 0}%`,
                            background: color,
                            boxShadow: `0 0 8px ${color}88`,
                            transition: 'width 1.4s ease-out',
                          }}
                        />
                      </div>
                      <p className="font-mono text-[9px] text-cyber-muted/50 truncate">{mLabel}</p>
                    </div>
                  )
                })}
              </div>

              {mlFakeProbability !== undefined && mlFakeProbability > 0.70 && (
                <div
                  className="rounded-lg px-4 py-3 border font-mono text-xs"
                  style={{ borderColor: '#ff336644', background: '#ff336611', color: '#ff3366' }}
                >
                  ML model detected high probability of AI-generated content
                  ({Math.round(mlFakeProbability * 100)}%). This signal has been factored into
                  the trust score.
                </div>
              )}
            </div>
          )}

          {/* Provenance + metadata */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Attribution chain */}
            <div className="cyber-card">
              <div className="flex items-center gap-2 mb-5">
                <Link2 className="w-4 h-4 text-cyber-cyan" />
                <p className="font-mono text-xs text-cyber-muted tracking-widest">ATTRIBUTION CHAIN</p>
              </div>

              <div className="flex flex-wrap items-center gap-1 mb-6">
                {prov.locations.map((loc, i) => (
                  <ProvenanceNode
                    key={loc}
                    label={loc.replace('-', ' ').toUpperCase()}
                    hash={prov.originalHash}
                    active={i === prov.locations.length - 1}
                    first={i === 0}
                    last={i === prov.locations.length - 1}
                  />
                ))}
              </div>

              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <Hash className="w-3.5 h-3.5 text-cyber-muted mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="font-mono text-[10px] text-cyber-muted">ORIGINAL HASH (SHA-256)</p>
                    <p className="font-mono text-xs text-cyber-cyan break-all">{prov.originalHash}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Clock className="w-3.5 h-3.5 text-cyber-muted shrink-0" />
                  <div>
                    <p className="font-mono text-[10px] text-cyber-muted">FIRST SEEN</p>
                    <p className="font-mono text-xs text-cyber-text">
                      {new Date(prov.firstSeen).toLocaleString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Lock className="w-3.5 h-3.5 text-cyber-muted shrink-0" />
                  <div>
                    <p className="font-mono text-[10px] text-cyber-muted">CRYPTOGRAPHIC SIGNATURES</p>
                    <p className="font-mono text-xs text-cyber-text">{prov.signatures} verified</p>
                  </div>
                </div>
              </div>
            </div>

            {/* File metadata */}
            <div className="cyber-card">
              <div className="flex items-center gap-2 mb-5">
                <FileType className="w-4 h-4 text-cyber-cyan" />
                <p className="font-mono text-xs text-cyber-muted tracking-widest">FILE METADATA</p>
              </div>
              <div className="space-y-3">
                {[
                  { label: 'FILENAME',    value: filename },
                  { label: 'TYPE',        value: type },
                  { label: 'SIZE',        value: size ?? 'N/A' },
                  { label: 'ANALYZED',    value: new Date(timestamp).toLocaleString() },
                  { label: 'ENGINE',      value: model ?? 'DeepScan v3.2' },
                  { label: 'SENSITIVITY', value: 'MEDIUM' },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-start justify-between gap-4 py-2 border-b border-cyber-border/30 last:border-0">
                    <span className="font-mono text-[10px] text-cyber-muted tracking-widest shrink-0">{label}</span>
                    <span className="font-mono text-xs text-cyber-text text-right break-all">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* AI interpretation */}
          <div className="cyber-card border-cyber-border/50">
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-4 h-4 text-cyber-cyan" />
              <p className="font-mono text-xs text-cyber-muted tracking-widest">AI INTERPRETATION</p>
            </div>
            <div className="bg-cyber-bg/50 rounded-lg p-4 border border-cyber-border/30">
              <p className="font-mono text-sm text-cyber-text leading-relaxed">
                {verdict === 'DEEPFAKE' ? (
                  <>
                    <span className="text-cyber-red font-semibold">HIGH CONFIDENCE DEEPFAKE DETECTED.</span>{' '}
                    Analysis indicates significant facial manipulation artifacts consistent with GAN-generated content.
                    Frequency domain anomalies and compression pattern irregularities suggest post-processing
                    consistent with face-swap or lip-sync manipulation. Recommend flagging for human review and
                    cross-referencing with known deepfake model signatures in the attribution database.
                  </>
                ) : verdict === 'SUSPICIOUS' ? (
                  <>
                    <span className="text-cyber-yellow font-semibold">SUSPICIOUS CONTENT — INCONCLUSIVE.</span>{' '}
                    Moderate indicators of manipulation detected, but confidence is below threshold for definitive
                    classification. Possible causes include heavy compression, steganographic embedding, or
                    minor post-processing. Recommend secondary analysis with elevated sensitivity and
                    manual forensic review before making attribution decisions.
                  </>
                ) : (
                  <>
                    <span className="text-cyber-green font-semibold">CONTENT APPEARS AUTHENTIC.</span>{' '}
                    No significant manipulation artifacts detected across facial, audio, metadata, or
                    frequency analysis modules. Attribution chain is intact with {prov.signatures} verified
                    cryptographic signatures. Trust score of {trustScore}/100 places this content in the
                    low-risk category. Standard monitoring protocols apply.
                  </>
                )}
              </p>
            </div>

            {/* Action buttons */}
            <div className="flex flex-wrap gap-3 mt-5">
              <button className="cyber-btn-primary flex items-center gap-2 py-2">
                <Shield className="w-4 h-4" />
                ESCALATE TO ANALYST
              </button>
              <button className="cyber-btn-success flex items-center gap-2 py-2">
                <CheckCircle className="w-4 h-4" />
                MARK REVIEWED
              </button>
              <button className="cyber-btn-danger flex items-center gap-2 py-2">
                <XCircle className="w-4 h-4" />
                FLAG & QUARANTINE
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
