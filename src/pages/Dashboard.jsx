import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  ScanSearch, ShieldAlert, ShieldCheck, Database,
  Upload, Bell, RefreshCw, Clock,
} from 'lucide-react'
import Sidebar  from '../components/Sidebar'
import StatCard from '../components/StatCard'
import { fetchStats, fetchWeekly, fetchMediaBreakdown, fetchRecent } from '../utils/api'
import { THREAT_FEED } from '../utils/mockData'

const TYPE_COLOR = { VIDEO: '#00d4ff', IMAGE: '#a855f7', AUDIO: '#00ff88' }

const VERDICT_COLORS = { DEEPFAKE: '#ff3366', SUSPICIOUS: '#ffcc00', AUTHENTIC: '#00ff88' }

function VerdictBadge({ v }) {
  const cls = v === 'DEEPFAKE' ? 'badge-danger' : v === 'SUSPICIOUS' ? 'badge-warning' : 'badge-safe'
  return <span className={cls}>{v}</span>
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-cyber-card border border-cyber-border rounded px-3 py-2 font-mono text-xs">
      <p className="text-cyber-cyan mb-1">{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color }}>{p.name}: {p.value}</p>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [time, setTime] = useState(new Date())
  const [feed, setFeed] = useState(THREAT_FEED)

  // Real API data
  const [stats,      setStats]      = useState(null)
  const [weekly,     setWeekly]     = useState([])
  const [breakdown,  setBreakdown]  = useState([])
  const [recent,     setRecent]     = useState([])

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  // Fetch all dashboard data on mount
  useEffect(() => {
    fetchStats().then(setStats).catch(() => {})

    fetchWeekly().then(data => {
      // API returns { days, analyzed, authentic, deepfakes } arrays — zip into chart rows
      if (!data?.days) return
      setWeekly(data.days.map((day, i) => ({
        day,
        analyzed:  data.analyzed[i],
        authentic: data.authentic[i],
        deepfakes: data.deepfakes[i],
      })))
    }).catch(() => {})

    fetchMediaBreakdown().then(data => {
      // API returns { VIDEO: n, IMAGE: n, AUDIO: n }
      const entries = Object.entries(data ?? {})
      const total = entries.reduce((s, [, v]) => s + v, 0) || 1
      setBreakdown(entries.map(([name, count]) => ({
        name,
        value: Math.round(count / total * 100),
        color: TYPE_COLOR[name] ?? '#4a6080',
      })))
    }).catch(() => {})

    fetchRecent().then(setRecent).catch(() => {})
  }, [])

  // Simulate live feed updates
  useEffect(() => {
    const t = setInterval(() => {
      setFeed(f => [
        { time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          event: ['Scan initiated on incoming file', 'Signature match in threat DB', 'New media hash recorded'][Math.floor(Math.random()*3)],
          severity: ['INFO','LOW','MED'][Math.floor(Math.random()*3)] },
        ...f.slice(0, 4),
      ])
    }, 8000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex h-screen bg-cyber-bg overflow-hidden">
      <Sidebar />

      <main className="flex-1 overflow-y-auto">
        {/* Topbar */}
        <header className="sticky top-0 z-10 bg-cyber-panel/90 backdrop-blur border-b border-cyber-border px-6 py-3 flex items-center justify-between">
          <div>
            <h1 className="font-mono text-lg font-bold text-cyber-cyan text-glow-cyan">OPERATIONS CENTER</h1>
            <p className="font-mono text-xs text-cyber-muted">Real-time deepfake detection & attribution</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 font-mono text-xs text-cyber-muted">
              <Clock className="w-3.5 h-3.5" />
              {time.toLocaleTimeString()}
            </div>
            <button
              onClick={() => {
                fetchStats().then(setStats).catch(() => {})
                fetchRecent().then(setRecent).catch(() => {})
              }}
              className="flex items-center gap-1.5 font-mono text-xs text-cyber-muted hover:text-cyber-cyan transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              REFRESH
            </button>
            <button className="relative">
              <Bell className="w-5 h-5 text-cyber-muted hover:text-cyber-cyan transition-colors" />
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-cyber-red rounded-full animate-pulse border border-cyber-panel" />
            </button>
            <button
              onClick={() => navigate('/upload')}
              className="cyber-btn-primary flex items-center gap-2 py-2"
            >
              <Upload className="w-4 h-4" />
              ANALYZE
            </button>
          </div>
        </header>

        <div className="p-6 space-y-6">
          {/* Stat cards */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard
              label="Files Analyzed"
              value={stats?.totalAnalyzed ?? '—'}
              sub={stats ? `${stats.deepfakesFound} deepfakes found` : 'Loading…'}
              icon={ScanSearch}
              color="cyan"
              trend={9}
            />
            <StatCard
              label="Deepfakes Found"
              value={stats?.deepfakesFound ?? '—'}
              sub={stats ? `${stats.totalAnalyzed ? Math.round(stats.deepfakesFound / stats.totalAnalyzed * 100) : 0}% detection rate` : 'Loading…'}
              icon={ShieldAlert}
              color="red"
              trend={-4}
            />
            <StatCard
              label="Avg Trust Score"
              value={stats?.avgTrustScore ?? '—'}
              sub="/100"
              icon={Database}
              color="purple"
              trend={2}
            />
            <StatCard
              label="Authentic Media"
              value={stats?.authenticCount ?? '—'}
              sub="Verified clean"
              icon={ShieldCheck}
              color="green"
              trend={5}
            />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            {/* Weekly trend */}
            <div className="xl:col-span-2 cyber-card">
              <p className="font-mono text-xs text-cyber-muted tracking-widest mb-4">WEEKLY ANALYSIS TREND</p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={weekly.length ? weekly : undefined}>
                  <CartesianGrid stroke="#1a3a5c" strokeDasharray="4 4" />
                  <XAxis dataKey="day" stroke="#4a6080" tick={{ fontFamily: 'Fira Code', fontSize: 11, fill: '#4a6080' }} />
                  <YAxis stroke="#4a6080" tick={{ fontFamily: 'Fira Code', fontSize: 11, fill: '#4a6080' }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend wrapperStyle={{ fontFamily: 'Fira Code', fontSize: 11 }} />
                  <Line type="monotone" dataKey="analyzed"  stroke="#00d4ff" strokeWidth={2} dot={{ fill: '#00d4ff', r: 3 }} name="Analyzed"  />
                  <Line type="monotone" dataKey="deepfakes" stroke="#ff3366" strokeWidth={2} dot={{ fill: '#ff3366', r: 3 }} name="Deepfakes" />
                  <Line type="monotone" dataKey="authentic" stroke="#00ff88" strokeWidth={2} dot={{ fill: '#00ff88', r: 3 }} name="Authentic" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Media type breakdown */}
            <div className="cyber-card flex flex-col">
              <p className="font-mono text-xs text-cyber-muted tracking-widest mb-4">MEDIA BREAKDOWN</p>
              <div className="flex-1 flex items-center justify-center">
                <PieChart width={160} height={160}>
                  <Pie data={breakdown} cx={75} cy={75} innerRadius={45} outerRadius={70}
                    dataKey="value" paddingAngle={3}>
                    {breakdown.map((e, i) => (
                      <Cell key={i} fill={e.color} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#0d1f38', border: '1px solid #1a3a5c', fontFamily: 'Fira Code', fontSize: 11 }}
                    itemStyle={{ color: '#c8d8e8' }}
                  />
                </PieChart>
              </div>
              <div className="space-y-2 mt-2">
                {breakdown.length > 0
                  ? breakdown.map(({ name, value, color }) => (
                    <div key={name} className="flex items-center justify-between font-mono text-xs">
                      <span className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                        <span className="text-cyber-muted">{name}</span>
                      </span>
                      <span style={{ color }}>{value}%</span>
                    </div>
                  ))
                  : <p className="font-mono text-xs text-cyber-muted text-center">No data yet</p>
                }
              </div>
            </div>
          </div>

          {/* Bottom row */}
          <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
            {/* Recent analyses */}
            <div className="xl:col-span-3 cyber-card">
              <div className="flex items-center justify-between mb-4">
                <p className="font-mono text-xs text-cyber-muted tracking-widest">RECENT ANALYSES</p>
                <button
                  onClick={() => navigate('/results')}
                  className="font-mono text-xs text-cyber-cyan hover:underline"
                >
                  VIEW ALL →
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-cyber-border/50">
                      {['ID', 'FILE', 'TYPE', 'TRUST', 'VERDICT', 'TIME'].map(h => (
                        <th key={h} className="font-mono text-[10px] text-cyber-muted text-left py-2 pr-4 tracking-widest">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {recent.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="font-mono text-xs text-cyber-muted py-6 text-center">
                          No analyses yet — upload a file to get started
                        </td>
                      </tr>
                    ) : recent.map((a) => (
                      <tr key={a.id}
                        onClick={() => navigate('/results', { state: { result: a } })}
                        className="border-b border-cyber-border/20 hover:bg-cyber-border/10 cursor-pointer transition-colors">
                        <td className="font-mono text-xs text-cyber-cyan py-2.5 pr-4">{a.id.slice(0, 8)}</td>
                        <td className="font-mono text-xs text-cyber-text py-2.5 pr-4 max-w-[120px] truncate" title={a.filename}>
                          {a.filename}
                        </td>
                        <td className="py-2.5 pr-4"><span className="badge-info">{a.type}</span></td>
                        <td className="font-mono text-xs py-2.5 pr-4" style={{
                          color: a.trustScore <= 32 ? '#ff3366' : a.trustScore <= 64 ? '#ffcc00' : '#00ff88'
                        }}>{a.trustScore}</td>
                        <td className="py-2.5 pr-4"><VerdictBadge v={a.verdict} /></td>
                        <td className="font-mono text-[10px] text-cyber-muted py-2.5">
                          {new Date(a.timestamp).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Live threat feed */}
            <div className="xl:col-span-2 cyber-card scan-container">
              <div className="flex items-center gap-2 mb-4">
                <span className="w-2 h-2 rounded-full bg-cyber-red animate-pulse" />
                <p className="font-mono text-xs text-cyber-muted tracking-widest">LIVE THREAT FEED</p>
              </div>
              <div className="space-y-3">
                {feed.map((item, i) => {
                  const cls = item.severity === 'HIGH' ? 'text-cyber-red'
                    : item.severity === 'MED' ? 'text-cyber-yellow'
                    : item.severity === 'LOW' ? 'text-cyber-green'
                    : 'text-cyber-muted'
                  return (
                    <div key={i} className="flex gap-3 animate-fade-in">
                      <span className="font-mono text-[10px] text-cyber-muted w-10 shrink-0 mt-0.5">{item.time}</span>
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-xs text-cyber-text leading-relaxed">{item.event}</p>
                        <p className={`font-mono text-[10px] ${cls}`}>{item.severity}</p>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Bar chart */}
          <div className="cyber-card">
            <p className="font-mono text-xs text-cyber-muted tracking-widest mb-4">DAILY DETECTION VOLUME</p>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={weekly} barGap={2}>
                <CartesianGrid stroke="#1a3a5c" strokeDasharray="4 4" vertical={false} />
                <XAxis dataKey="day" stroke="#4a6080" tick={{ fontFamily: 'Fira Code', fontSize: 11, fill: '#4a6080' }} />
                <YAxis stroke="#4a6080" tick={{ fontFamily: 'Fira Code', fontSize: 11, fill: '#4a6080' }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="deepfakes" fill="#ff3366" radius={[3,3,0,0]} name="Deepfakes" />
                <Bar dataKey="authentic" fill="#00ff88" radius={[3,3,0,0]} name="Authentic" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </main>
    </div>
  )
}
