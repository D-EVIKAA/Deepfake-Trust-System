/**
 * API client for the Deepfake Trust & Attribution System backend.
 * The Vite dev proxy forwards /api  →  http://localhost:8000/api
 */

const API_BASE = '/api'

/**
 * Upload a media file and receive a full analysis report.
 *
 * @param {File}   file        - the media file to analyse
 * @param {object} options
 * @param {string} options.sensitivity  - "LOW" | "MEDIUM" | "HIGH"
 * @param {object} options.checks       - { facial, audio, metadata, frequency }
 * @returns {Promise<object>}  analysis result (matches Results.jsx data shape)
 */
export async function analyzeFile(file, { sensitivity = 'MEDIUM', checks = {} } = {}) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('sensitivity', sensitivity)
  formData.append(
    'checks',
    JSON.stringify({
      facial:    checks.facial    ?? true,
      audio:     checks.audio     ?? true,
      metadata:  checks.metadata  ?? true,
      frequency: checks.frequency ?? true,
    }),
  )

  let res
  try {
    res = await fetch(`${API_BASE}/analyze`, { method: 'POST', body: formData })
  } catch (networkErr) {
    throw new Error(
      'Cannot reach the analysis backend. ' +
      'Make sure it is running: cd backend && uvicorn main:app --reload',
    )
  }

  if (!res.ok) {
    let detail = `Backend error ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch { /* ignore parse error */ }
    throw new Error(detail)
  }

  return res.json()
}

/**
 * Quick liveness check — resolves true if the backend responds, false otherwise.
 */
export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      signal: AbortSignal.timeout(3500),
    })
    return res.ok
  } catch {
    return false
  }
}

/** Fetch overall dashboard stats. */
export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`)
  if (!res.ok) throw new Error(`Stats fetch failed: ${res.status}`)
  return res.json()
}

/** Fetch last-7-days weekly trend data. */
export async function fetchWeekly() {
  const res = await fetch(`${API_BASE}/weekly`)
  if (!res.ok) throw new Error(`Weekly fetch failed: ${res.status}`)
  return res.json()
}

/** Fetch media type breakdown (VIDEO / IMAGE / AUDIO counts). */
export async function fetchMediaBreakdown() {
  const res = await fetch(`${API_BASE}/media-breakdown`)
  if (!res.ok) throw new Error(`Media breakdown fetch failed: ${res.status}`)
  return res.json()
}

/** Fetch the 10 most recent analysis records. */
export async function fetchRecent() {
  const res = await fetch(`${API_BASE}/recent`)
  if (!res.ok) throw new Error(`Recent fetch failed: ${res.status}`)
  return res.json()
}

/**
 * Download a plain-text forensic report for the given analysis ID.
 * Triggers a browser file-save dialog.
 */
export async function downloadReport(id) {
  const res = await fetch(`${API_BASE}/report/${id}`)
  if (!res.ok) {
    const msg = res.status === 404
      ? 'Report not found — analysis may not have been saved to the database'
      : `Download failed (HTTP ${res.status})`
    throw new Error(msg)
  }
  const blob = await res.blob()
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `deepfake_report_${id}.txt`
  // Must be in DOM for Firefox; revoke only after browser queues the download
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}
