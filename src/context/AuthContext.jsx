import { createContext, useContext, useState } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const stored = sessionStorage.getItem('dts_user')
    return stored ? JSON.parse(stored) : null
  })

  function login(username, password) {
    // Demo: accept any non-empty credentials
    if (!username || !password) return false
    const u = {
      id: 'USR-' + Math.random().toString(36).slice(2, 8).toUpperCase(),
      username,
      role: 'ANALYST',
      clearance: 'LEVEL-3',
      loginTime: new Date().toISOString(),
    }
    setUser(u)
    sessionStorage.setItem('dts_user', JSON.stringify(u))
    return true
  }

  function logout() {
    setUser(null)
    sessionStorage.removeItem('dts_user')
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
