import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Upload, Shield, Activity,
  Database, Settings, LogOut, Cpu, AlertTriangle,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { label: 'Dashboard',  to: '/',        icon: LayoutDashboard },
  { label: 'Upload',     to: '/upload',  icon: Upload          },
  { label: 'Results',    to: '/results', icon: Shield          },
]

const SECONDARY = [
  { label: 'Activity Log', icon: Activity     },
  { label: 'Evidence DB',  icon: Database     },
  { label: 'Settings',     icon: Settings     },
]

export default function Sidebar() {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()

  return (
    <aside className="w-64 min-h-screen bg-cyber-panel border-r border-cyber-border flex flex-col shrink-0">
      {/* Logo */}
      <div className="p-6 border-b border-cyber-border">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-lg bg-cyber-cyan/10 border border-cyber-cyan/40 flex items-center justify-center animate-pulse-slow">
              <Shield className="w-5 h-5 text-cyber-cyan" />
            </div>
            <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-cyber-green rounded-full border border-cyber-panel animate-pulse" />
          </div>
          <div>
            <p className="font-mono text-xs text-cyber-cyan tracking-widest">DEEPFAKE</p>
            <p className="font-mono text-xs text-cyber-muted">TRUST SYSTEM</p>
          </div>
        </div>
      </div>

      {/* User badge */}
      <div className="px-4 py-3 border-b border-cyber-border/50">
        <div className="flex items-center gap-2 bg-cyber-card rounded-lg px-3 py-2 border border-cyber-border/50">
          <div className="w-7 h-7 rounded bg-cyber-cyan/10 border border-cyber-cyan/30 flex items-center justify-center">
            <Cpu className="w-3.5 h-3.5 text-cyber-cyan" />
          </div>
          <div className="min-w-0">
            <p className="font-mono text-xs text-cyber-text truncate">{user?.username}</p>
            <p className="font-mono text-[10px] text-cyber-muted">{user?.clearance}</p>
          </div>
          <span className="ml-auto badge-safe text-[10px] shrink-0">ONLINE</span>
        </div>
      </div>

      {/* Primary nav */}
      <nav className="flex-1 p-3 space-y-1">
        <p className="font-mono text-[10px] text-cyber-muted tracking-widest px-4 py-2">MODULES</p>
        {NAV.map(({ label, to, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className={`nav-item ${pathname === to ? 'active' : ''}`}
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span>{label}</span>
            {pathname === to && (
              <span className="ml-auto w-1.5 h-1.5 rounded-full bg-cyber-cyan animate-pulse" />
            )}
          </Link>
        ))}

        <div className="pt-4">
          <p className="font-mono text-[10px] text-cyber-muted tracking-widest px-4 py-2">TOOLS</p>
          {SECONDARY.map(({ label, icon: Icon }) => (
            <button key={label} className="nav-item w-full text-left opacity-50 cursor-not-allowed">
              <Icon className="w-4 h-4 shrink-0" />
              <span>{label}</span>
              <span className="ml-auto badge-warning text-[9px] shrink-0">SOON</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Threat level */}
      <div className="px-4 py-3 border-t border-cyber-border/50">
        <div className="bg-cyber-red/10 border border-cyber-red/20 rounded-lg px-3 py-2 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-cyber-red animate-pulse" />
          <div>
            <p className="font-mono text-[10px] text-cyber-red">THREAT LEVEL: HIGH</p>
            <p className="font-mono text-[9px] text-cyber-muted">41 detections today</p>
          </div>
        </div>
      </div>

      {/* Logout */}
      <div className="p-3 border-t border-cyber-border">
        <button
          onClick={logout}
          className="nav-item w-full text-left text-cyber-red/70 hover:text-cyber-red hover:bg-cyber-red/10"
        >
          <LogOut className="w-4 h-4" />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  )
}
