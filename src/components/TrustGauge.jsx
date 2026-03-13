import { useEffect, useState } from 'react'

function getScoreConfig(score) {
  if (score <= 32)  return { label: 'DEEPFAKE',    color: '#ff3366', glow: 'glow-red',   bg: 'bg-cyber-red/10',   border: 'border-cyber-red/30'   }
  if (score <= 64)  return { label: 'SUSPICIOUS',  color: '#ffcc00', glow: 'glow-yellow',bg: 'bg-cyber-yellow/10',border: 'border-cyber-yellow/30' }
  if (score <= 85)  return { label: 'LOW RISK',    color: '#00d4ff', glow: 'glow-cyan',  bg: 'bg-cyber-cyan/10',  border: 'border-cyber-cyan/30'   }
  return              { label: 'AUTHENTIC',   color: '#00ff88', glow: 'glow-green', bg: 'bg-cyber-green/10', border: 'border-cyber-green/30'  }
}

export default function TrustGauge({ score = 0, size = 200 }) {
  const [animated, setAnimated] = useState(0)
  const config   = getScoreConfig(score)
  const radius   = size / 2 - 16
  const circ     = 2 * Math.PI * radius
  // Arc: 270° sweep starting from bottom-left (135deg)
  const arc      = circ * 0.75
  const offset   = arc - (animated / 100) * arc
  const viewBox  = `0 0 ${size} ${size}`
  const cx = size / 2
  const cy = size / 2

  useEffect(() => {
    const t = setTimeout(() => setAnimated(score), 300)
    return () => clearTimeout(t)
  }, [score])

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={viewBox} className="drop-shadow-lg">
          {/* Track */}
          <circle
            cx={cx} cy={cy} r={radius}
            fill="none"
            stroke="#1a3a5c"
            strokeWidth="12"
            strokeDasharray={`${arc} ${circ - arc}`}
            strokeDashoffset={0}
            strokeLinecap="round"
            transform={`rotate(135 ${cx} ${cy})`}
          />
          {/* Filled arc */}
          <circle
            cx={cx} cy={cy} r={radius}
            fill="none"
            stroke={config.color}
            strokeWidth="12"
            strokeDasharray={`${arc} ${circ - arc}`}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform={`rotate(135 ${cx} ${cy})`}
            style={{
              transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)',
              filter: `drop-shadow(0 0 8px ${config.color})`,
            }}
          />
          {/* Tick marks */}
          {[0, 25, 50, 75, 100].map((pct) => {
            const angle = (135 + pct * 2.7) * (Math.PI / 180)
            const r2 = radius + 18
            const x1 = cx + (radius + 4) * Math.cos(angle)
            const y1 = cy + (radius + 4) * Math.sin(angle)
            const x2 = cx + r2 * Math.cos(angle)
            const y2 = cy + r2 * Math.sin(angle)
            return <line key={pct} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#1a3a5c" strokeWidth="2" />
          })}
        </svg>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="font-mono font-bold leading-none"
            style={{ fontSize: size * 0.22, color: config.color, textShadow: `0 0 20px ${config.color}88` }}
          >
            {animated}
          </span>
          <span className="font-mono text-cyber-muted mt-1" style={{ fontSize: size * 0.065 }}>
            TRUST SCORE
          </span>
        </div>
      </div>

      {/* Verdict badge */}
      <div className={`px-5 py-2 rounded-lg border ${config.bg} ${config.border} text-center`}>
        <p className="font-mono font-bold tracking-widest" style={{ color: config.color, fontSize: 13 }}>
          {config.label}
        </p>
        <p className="font-mono text-cyber-muted text-[10px] mt-0.5">
          {score <= 32  ? 'AI-generated content detected'
          : score <= 64 ? 'Manipulation indicators present'
          : score <= 85 ? 'Minor anomalies detected'
          :               'No manipulation detected'}
        </p>
      </div>

      {/* Score scale */}
      <div className="flex gap-1 items-center font-mono text-[10px] text-cyber-muted">
        <span className="text-cyber-red">0</span>
        <div className="w-24 h-1.5 rounded-full overflow-hidden flex">
          <div className="flex-1 bg-cyber-red/60" />
          <div className="flex-1 bg-cyber-yellow/60" />
          <div className="flex-1 bg-cyber-cyan/60" />
          <div className="flex-1 bg-cyber-green/60" />
        </div>
        <span className="text-cyber-green">100</span>
      </div>
    </div>
  )
}
