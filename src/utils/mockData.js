// Simulated analysis results for demo purposes

export const RECENT_ANALYSES = [
  {
    id: 'ANA-001',
    filename: 'press_conference_clip.mp4',
    type: 'VIDEO',
    trustScore: 22,
    verdict: 'DEEPFAKE',
    timestamp: '2026-03-13T10:42:00Z',
    size: '48.2 MB',
    duration: '1m 34s',
    analyst: 'auto',
  },
  {
    id: 'ANA-002',
    filename: 'profile_photo_leak.jpg',
    type: 'IMAGE',
    trustScore: 67,
    verdict: 'SUSPICIOUS',
    timestamp: '2026-03-13T09:18:00Z',
    size: '3.7 MB',
    duration: null,
    analyst: 'auto',
  },
  {
    id: 'ANA-003',
    filename: 'ceo_audio_statement.mp3',
    type: 'AUDIO',
    trustScore: 91,
    verdict: 'AUTHENTIC',
    timestamp: '2026-03-13T08:55:00Z',
    size: '12.1 MB',
    duration: '4m 22s',
    analyst: 'auto',
  },
  {
    id: 'ANA-004',
    filename: 'news_anchor_interview.mp4',
    type: 'VIDEO',
    trustScore: 38,
    verdict: 'SUSPICIOUS',
    timestamp: '2026-03-12T22:10:00Z',
    size: '112 MB',
    duration: '8m 01s',
    analyst: 'auto',
  },
  {
    id: 'ANA-005',
    filename: 'government_id_scan.png',
    type: 'IMAGE',
    trustScore: 88,
    verdict: 'AUTHENTIC',
    timestamp: '2026-03-12T17:30:00Z',
    size: '1.2 MB',
    duration: null,
    analyst: 'auto',
  },
]

export const WEEKLY_STATS = [
  { day: 'Mon', analyzed: 14, deepfakes: 3, authentic: 11 },
  { day: 'Tue', analyzed: 22, deepfakes: 7, authentic: 15 },
  { day: 'Wed', analyzed: 18, deepfakes: 4, authentic: 14 },
  { day: 'Thu', analyzed: 31, deepfakes: 12, authentic: 19 },
  { day: 'Fri', analyzed: 27, deepfakes: 8, authentic: 19 },
  { day: 'Sat', analyzed: 9,  deepfakes: 2, authentic: 7  },
  { day: 'Sun', analyzed: 16, deepfakes: 5, authentic: 11 },
]

export const MEDIA_BREAKDOWN = [
  { name: 'Video',  value: 52, color: '#00d4ff' },
  { name: 'Image',  value: 33, color: '#a855f7' },
  { name: 'Audio',  value: 15, color: '#00ff88' },
]

export const THREAT_FEED = [
  { time: '10:42',  event: 'Deepfake detected in uploaded video', severity: 'HIGH'   },
  { time: '10:18',  event: 'Suspicious manipulation pattern found', severity: 'MED'  },
  { time: '09:55',  event: 'New AI model signature catalogued', severity: 'INFO'     },
  { time: '09:30',  event: 'Attribution chain verified — 4 hops', severity: 'LOW'   },
  { time: '09:12',  event: 'Batch scan completed — 7 files clean', severity: 'INFO' },
]

export const DASHBOARD_STATS = {
  totalAnalyzed:   137,
  deepfakesFound:  41,
  avgTrustScore:   71,
  sourcesVerified: 89,
}

// Simulate running an analysis on an uploaded file
export function runMockAnalysis(file) {
  return new Promise((resolve) => {
    setTimeout(() => {
      const isDeepfake = Math.random() < 0.4
      const isSuspicious = !isDeepfake && Math.random() < 0.35
      const trustScore = isDeepfake
        ? Math.floor(Math.random() * 28) + 5         // 5–32
        : isSuspicious
        ? Math.floor(Math.random() * 30) + 35        // 35–64
        : Math.floor(Math.random() * 20) + 78        // 78–97

      const verdict = isDeepfake ? 'DEEPFAKE' : isSuspicious ? 'SUSPICIOUS' : 'AUTHENTIC'

      resolve({
        id: 'ANA-' + Math.random().toString(36).slice(2, 8).toUpperCase(),
        filename: file.name,
        size: (file.size / (1024 * 1024)).toFixed(2) + ' MB',
        type: file.type.startsWith('video') ? 'VIDEO'
            : file.type.startsWith('audio') ? 'AUDIO'
            : 'IMAGE',
        trustScore,
        verdict,
        timestamp: new Date().toISOString(),
        confidence: Math.floor(Math.random() * 10) + 88,
        model: 'DeepScan v3.2',
        checks: {
          facialInconsistency:  isDeepfake   ? Math.floor(Math.random() * 40) + 60 : Math.floor(Math.random() * 20),
          audioVisualSync:      isSuspicious ? Math.floor(Math.random() * 30) + 40 : Math.floor(Math.random() * 15),
          metadataIntegrity:    Math.random() > 0.3 ? Math.floor(Math.random() * 10) : Math.floor(Math.random() * 50) + 30,
          compressionArtifacts: isDeepfake   ? Math.floor(Math.random() * 30) + 50 : Math.floor(Math.random() * 20),
          frequencyAnalysis:    isDeepfake   ? Math.floor(Math.random() * 35) + 55 : Math.floor(Math.random() * 18),
          temporalConsistency:  isSuspicious ? Math.floor(Math.random() * 25) + 30 : Math.floor(Math.random() * 12),
        },
        provenance: {
          originalHash: '0x' + Math.random().toString(16).slice(2, 34),
          firstSeen: new Date(Date.now() - Math.random() * 7 * 86400000).toISOString(),
          locations: ['upload-endpoint', 'analysis-cluster', 'attribution-db'],
          signatures: Math.floor(Math.random() * 3) + 1,
        },
      })
    }, 3000 + Math.random() * 2000) // 3–5s simulated processing
  })
}
