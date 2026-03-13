export default function StatCard({ label, value, sub, icon: Icon, color = 'cyan', trend }) {
  const colors = {
    cyan:   { text: 'text-cyber-cyan',   bg: 'bg-cyber-cyan/10',   border: 'border-cyber-cyan/20'   },
    green:  { text: 'text-cyber-green',  bg: 'bg-cyber-green/10',  border: 'border-cyber-green/20'  },
    red:    { text: 'text-cyber-red',    bg: 'bg-cyber-red/10',    border: 'border-cyber-red/20'    },
    purple: { text: 'text-cyber-purple', bg: 'bg-cyber-purple/10', border: 'border-cyber-purple/20' },
  }
  const c = colors[color] ?? colors.cyan

  return (
    <div className="cyber-card group hover:border-cyber-border transition-all duration-300 animate-slide-up">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-10 h-10 rounded-lg ${c.bg} border ${c.border} flex items-center justify-center`}>
          <Icon className={`w-5 h-5 ${c.text}`} />
        </div>
        {trend !== undefined && (
          <span className={`font-mono text-xs ${trend >= 0 ? 'text-cyber-green' : 'text-cyber-red'}`}>
            {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <p className={`font-mono text-3xl font-bold ${c.text} mb-1`}>{value}</p>
      <p className="text-cyber-text text-sm font-medium mb-0.5">{label}</p>
      {sub && <p className="font-mono text-[11px] text-cyber-muted">{sub}</p>}
    </div>
  )
}
