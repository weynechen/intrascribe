'use client'

// Extend window object for global audio player control
declare global {
  interface Window {
    audioPlayerSeekTo?: (time: number) => void
  }
}

// API response interface for rename speaker
interface RenameSpeakerResponse {
  success: boolean
  message?: string
}

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { Sidebar } from '@/components/sidebar'
import { FileList } from '@/components/file-list'
import { Header } from '@/components/header'
import { TranscriptView } from '@/components/transcript-view'
import { AISummaryPanel } from '@/components/ai-summary-panel'
import { TemplateManager } from '@/components/template-manager'
import { useAuth } from '@/hooks/useAuth'
import { useRecordingSessions } from '@/hooks/useRecordingSessions'
import { toast } from 'sonner'
import { TranscriptEvent } from '@/lib/supabase-client'
import { apiPost, httpClient } from '@/lib/api-client'

interface TranscriptItem {
  id: string
  timestamp: string
  speaker?: string
  text: string
}

interface RecordingSession {
  id: string
  title: string
  status: 'created' | 'recording' | 'processing' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  duration_seconds?: number
  transcriptions?: Array<{
    id: string
    content: string
    segments: unknown
    created_at: string
  }>
  ai_summaries?: Array<{
    id: string
    summary: string
  }>
}

export default function HomePage() {
  const router = useRouter()
  const { user, session, loading: authLoading } = useAuth()
  const { 
    sessions, 
    deleteSession,
    generateSummary,
    generateTitle,
    fetchSessions,
    finalizeSession
  } = useRecordingSessions()
  
  // Create APIClient instance for batch transcription
  const [apiClient, setApiClient] = useState<{ 
    updateSessionTemplate: (sessionId: string, templateId: string) => Promise<{ message: string; session_id: string; template_id: string }>
    retranscribeSession: (sessionId: string) => Promise<{ success: boolean; message: string; session_id: string; status: string }>
  } | null>(null)
  
  useEffect(() => {
    if (session?.access_token) {
      import('@/lib/supabase').then(({ APIClient }) => {
        const client = new APIClient('/api/v1', () => session.access_token)
        setApiClient(client)
      })
    }
  }, [session?.access_token])
  
  const [currentView, setCurrentView] = useState('record')
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [currentTranscript, setCurrentTranscript] = useState<TranscriptItem[]>([])
  const [fullTranscriptText, setFullTranscriptText] = useState<string>('')
  const [isRecording, setIsRecording] = useState(false)
  // Audio playback sync states
  const [currentAudioTime, setCurrentAudioTime] = useState(0)
  
  // AI Summary states
  const [showAISummaryPanel, setShowAISummaryPanel] = useState(false)
  const [isLoadingSummary, setIsLoadingSummary] = useState(false)
  const [aiSummary, setAiSummary] = useState<string>('')
  const [aiTitle, setAiTitle] = useState<string>('')
  const [aiSummaryId, setAiSummaryId] = useState<string>('')
  const [transcriptionId, setTranscriptionId] = useState<string>('')
  
  // Add current recording session ID state
  const [currentRecordingSessionId, setCurrentRecordingSessionId] = useState<string>('')
  
  // Audio refresh ref
  const refreshAudioRef = useRef<(() => Promise<void>) | null>(null)
  
  // Template selection state - temporarily remove unused state
  // const [selectedTemplateId, setSelectedTemplateId] = useState<string | undefined>()

  // Handle real-time transcription data
  const handleTranscript = useCallback((transcriptEvent: TranscriptEvent) => {
    if (transcriptEvent.text.trim()) {
      // Check if it's complete text (summary when recording ends)
      if (transcriptEvent.text.length > 100 && transcriptEvent.text.includes(' ') && !transcriptEvent.timestamp) {
        // This is the complete transcription text when recording ends
        setFullTranscriptText(transcriptEvent.text)
        
        // Split complete text into sentences for display
        const sentences = transcriptEvent.text.split(/[。！？.!?]/).filter(s => s.trim())
        const transcriptItems = sentences.map((sentence, index) => ({
          id: `final_${index}`,
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          speaker: transcriptEvent.speaker || undefined,
          text: sentence.trim() + (index < sentences.length - 1 ? '。' : '')
        })).filter(item => item.text.length > 1)
        
        setCurrentTranscript(transcriptItems)
        
        // After recording ends, if there's a recording session ID, automatically select it
        if (currentRecordingSessionId) {
          setSelectedSessionId(currentRecordingSessionId)
        }
      } else {
        // Real-time transcription segment - use real data returned from backend
        const newItem: TranscriptItem = {
          id: `live_${transcriptEvent.index}_${Date.now()}`,
          timestamp: transcriptEvent.timestamp || new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          speaker: transcriptEvent.speaker && transcriptEvent.speaker !== 'unknown' ? transcriptEvent.speaker : undefined,
          text: transcriptEvent.text.trim()
        }
        
        // Directly append new transcription items instead of replacing
        setCurrentTranscript(prev => [...prev, newItem])
      }
    }
  }, [currentRecordingSessionId])

  const handleRecordingStateChange = useCallback(async (recording: boolean) => {
    setIsRecording(recording)
    
    if (recording) {
      // Start recording - clear current state
      setCurrentTranscript([])
      setFullTranscriptText('')
      setAiSummary('')
      setAiTitle('')
      setAiSummaryId('')
      setTranscriptionId('')
      setShowAISummaryPanel(false)
      // Don't clear selectedSessionId, let user see currently selected session
    } else {
      // Recording ended - call finalize session to save transcription data
      toast.info('Recording ended, saving transcription data...', {
        duration: 5000
      })
      
      // Call finalize session to save Redis data to database
      if (currentRecordingSessionId) {
        try {
          await finalizeSession(currentRecordingSessionId)
          toast.success('Transcription data saved to database')
          
          // Wait a moment, then manually refresh audio files
          setTimeout(async () => {
            if (refreshAudioRef.current) {
              await refreshAudioRef.current()
            }
          }, 3000)
          
        } catch (error) {
          toast.error('Failed to save transcription data, but real-time data is still available')
        }
      } else {
      }
      
      // Refresh session data to get latest status
      setTimeout(() => {
        try {
          fetchSessions(true)
        } catch (e) {
        }
      }, 1200)
      
      setTimeout(() => {
        setCurrentRecordingSessionId('')
      }, 2000) // Give data update some time
    }
  }, [fetchSessions, finalizeSession, currentRecordingSessionId])

  // Handle recording session creation
  const handleSessionCreated = useCallback((roomName: string) => {
    // Extract real session ID from room name
    let actualSessionId = roomName
    if (roomName.startsWith('intrascribe_room_')) {
      actualSessionId = roomName.replace('intrascribe_room_', '')
    }
    
    setCurrentRecordingSessionId(actualSessionId)
    // Auto-select newly created session
    setSelectedSessionId(actualSessionId)
  }, [])

  // Handle audio time updates for transcript highlighting
  const handleAudioTimeUpdate = useCallback((currentTime: number) => {
    setCurrentAudioTime(currentTime)
  }, [])

  // Handle seek to specific time when transcript card is clicked
  const handleSeekToTime = useCallback((timeInSeconds: number) => {
    // Use the global function exposed by AudioPlayer
    if (window.audioPlayerSeekTo) {
      window.audioPlayerSeekTo(timeInSeconds)
      setCurrentAudioTime(timeInSeconds)
    }
  }, [])

  // Extract session data processing logic as independent function
  const processSessionData = useCallback((selectedSession: RecordingSession) => {
    if (isRecording) {
      toast.warning('Recording in progress, cannot switch session')
      return
    }

    // If selecting the same session and AI summary panel is showing, don't reload
    if (selectedSessionId === selectedSession.id && showAISummaryPanel) {
      return
    }

    setSelectedSessionId(selectedSession.id)
    
    // Clear current state
    setCurrentTranscript([])
    setFullTranscriptText('')
    setAiSummary('')
    setAiTitle('')
    setAiSummaryId('')
    setTranscriptionId('')
    setShowAISummaryPanel(false)
    
    // Restore transcription content
    if (selectedSession.transcriptions && selectedSession.transcriptions.length > 0) {
      const transcription = selectedSession.transcriptions[0]
      
      setFullTranscriptText(transcription.content)
      setTranscriptionId(transcription.id)
      
      // Prioritize using segments field to build transcript items
      let segments = transcription.segments
      
      // Handle possible data format issues
      if (segments && typeof segments === 'string') {
        try {
          segments = JSON.parse(segments)
        } catch (error) {
          segments = []
        }
      }
      
      if (segments && Array.isArray(segments) && segments.length > 0) {
        
        // Validate each segment
        const validSegments = segments.filter((segment: unknown, _index: number) => {
          const seg = segment as { text?: string; speaker?: string; start_time?: number; end_time?: number; index?: number }
          const isValid = seg && seg.text && typeof seg.text === 'string' && seg.text.trim()
          if (!isValid) {
          }
          return isValid
        })
        
        
        if (validSegments.length > 0) {
          const transcriptItems = validSegments.map((segment: unknown, index: number) => {
            const seg = segment as { text: string; speaker?: string; start_time?: number; end_time?: number; index?: number }
            return {
              id: `${transcription.id}_segment_${seg.index || index}`,
              timestamp: seg.start_time !== undefined && seg.end_time !== undefined
                ? `[${formatSegmentTime(seg.start_time)},${formatSegmentTime(seg.end_time)}]`
                : new Date(transcription.created_at).toLocaleTimeString('zh-CN', { hour12: false }),
              speaker: seg.speaker && seg.speaker !== 'unknown' ? seg.speaker : undefined,
              text: seg.text.trim()
            }
          })
          
          setCurrentTranscript(transcriptItems)
        } else {
          // Fallback to content splitting
          if (transcription.content && transcription.content.trim()) {
            const lines = transcription.content.split('\n').filter((line: string) => line.trim())
            const transcriptItems = lines.map((line: string, index: number) => ({
              id: `${transcription.id}_${index}`,
              timestamp: new Date(transcription.created_at).toLocaleTimeString('zh-CN', { hour12: false }),
              text: line.trim()
            }))
            setCurrentTranscript(transcriptItems)
          } else {
            setCurrentTranscript([])
          }
        }
      } else {
        
        // If no segments, fallback to splitting content text
        if (transcription.content && transcription.content.trim()) {
          const lines = transcription.content.split('\n').filter((line: string) => line.trim())
          
          const transcriptItems = lines.map((line: string, index: number) => ({
            id: `${transcription.id}_${index}`,
            timestamp: new Date(transcription.created_at).toLocaleTimeString('zh-CN', { hour12: false }),
            text: line.trim()
          }))
          
          setCurrentTranscript(transcriptItems)
        } else {
          setCurrentTranscript([])
        }
      }
      
      // Restore AI summary
      if (selectedSession.ai_summaries && selectedSession.ai_summaries.length > 0) {
        const summary = selectedSession.ai_summaries[0]
        setAiSummary(summary.summary)
        setAiSummaryId(summary.id)
        setShowAISummaryPanel(true)
      }
      
      // Set title
      setAiTitle(selectedSession.title)
    }
  }, [isRecording, selectedSessionId, showAISummaryPanel])

  // Handle session selection
  const handleSessionSelect = useCallback(async (sessionId: string) => {
    
    // Restore state from session data
    const selectedSession = sessions.find(s => s.id === sessionId)
    if (selectedSession) {
      
      // Add more detailed session data debug info
      
      // Key fix: if session is completed but has no transcription data, force refresh
      if (selectedSession.status === 'completed' && 
          (!selectedSession.transcriptions || selectedSession.transcriptions.length === 0)) {
        await fetchSessions()
        // Re-fetch session data after refresh
        const refreshedSession = sessions.find(s => s.id === sessionId)
        if (refreshedSession) {
          // Continue processing with refreshed data
          processSessionData(refreshedSession)
        }
        return
      }
      
      processSessionData(selectedSession)
    } else {
      console.warn('⚠️ 未找到指定的会话:', sessionId)
    }
  }, [sessions, fetchSessions, processSessionData])

  // AI summary generation handler
  const handleAISummary = useCallback(async (templateId?: string) => {
    if (!fullTranscriptText && currentTranscript.length === 0) {
      toast.error('No transcription content available, cannot generate summary')
      return
    }

    const transcriptText = fullTranscriptText || currentTranscript.map(t => t.text).join(' ')
    
    if (!transcriptText.trim()) {
      toast.error('Transcription content is empty, cannot generate summary')
      return
    }

    // Ensure valid session ID
    const sessionId = selectedSessionId || currentRecordingSessionId
    if (!sessionId) {
      toast.error('Cannot find valid recording session, please select a recording first')
      return
    }

    // Use provided template ID or default
    let finalTemplateId = templateId
    if (!finalTemplateId) {
      const currentSession = sessions.find(s => s.id === sessionId)
      if (!currentSession) {
        toast.error('Cannot find corresponding recording session, unable to generate summary')
        return
      }
      finalTemplateId = '' // Use default template
    }

    setShowAISummaryPanel(true)
    setIsLoadingSummary(true)

    try {
      // Generate AI summary with specified template
      const summaryResult = await generateSummary(sessionId, transcriptText, finalTemplateId)
      if (summaryResult) {
        setAiSummary(summaryResult.summary)
        
        // Get AI summary ID from refreshed session data
        const refreshedSession = sessions.find(s => s.id === sessionId)
        if (refreshedSession?.ai_summaries && refreshedSession.ai_summaries.length > 0) {
          const latestSummary = refreshedSession.ai_summaries[0]
          setAiSummaryId(latestSummary.id)
        }
        
        // Generate title after summary
        const titleResult = await generateTitle(sessionId, transcriptText, summaryResult.summary)
        if (titleResult) {
          setAiTitle(titleResult.title)
        }
        
        toast.success('AI summary and title generation completed')
      }
    } catch (error) {
      console.error('Failed to generate AI summary:', error)
      toast.error('Failed to generate AI summary')
    } finally {
      setIsLoadingSummary(false)
    }
  }, [fullTranscriptText, currentTranscript, selectedSessionId, currentRecordingSessionId, generateSummary, generateTitle, sessions])

  // Handle template selection
  const handleTemplateSelect = useCallback(async (sessionId: string, templateId: string) => {
    try {
      // Update session template selection
      if (apiClient) {
        await apiClient.updateSessionTemplate(sessionId, templateId)
        await fetchSessions()
        toast.success('Template selection saved')
      } else {
        toast.error('Unable to save template selection')
      }
    } catch (error) {
      console.error('Failed to update session template:', error)
      toast.error('Failed to save template selection')
    }
  }, [apiClient, fetchSessions])

  // Handle session deletion
  const handleDeleteSession = useCallback(async (sessionId: string) => {
    if (window.confirm('Are you sure you want to delete this recording? This action cannot be undone.')) {
      try {
        await deleteSession(sessionId)
        // Clear state if deleting currently selected session
        if (selectedSessionId === sessionId) {
          setSelectedSessionId('')
          setCurrentTranscript([])
          setFullTranscriptText('')
          setAiSummary('')
          setAiTitle('')
          setAiSummaryId('')
          setTranscriptionId('')
          setShowAISummaryPanel(false)
          setCurrentAudioTime(0)
          
          // Reset audio player
          if (window.audioPlayerSeekTo) {
            try {
              window.audioPlayerSeekTo(0)
            } catch (error) {
              console.log('Error resetting audio player:', error)
            }
          }
        }
      } catch (error) {
        console.error('Failed to delete session:', error)
        toast.error('Failed to delete recording session')
      }
    }
  }, [deleteSession, selectedSessionId])

  // Handle AI summary updates
  const handleSummaryUpdate = useCallback((summary: string) => {
    setAiSummary(summary)
  }, [])

  // Handle AI title updates
  const handleTitleUpdate = useCallback((title: string) => {
    setAiTitle(title)
  }, [])

  // Handle session data refresh
  const handleRefreshSessions = useCallback(() => {
    if (user?.id) {
      fetchSessions()
    }
  }, [user?.id, fetchSessions])

  // Format duration in MM:SS format
  const formatDuration = (durationSeconds: number) => {
    if (!durationSeconds || durationSeconds <= 0) return "00:00"
    const minutes = Math.floor(durationSeconds / 60)
    const seconds = Math.floor(durationSeconds % 60)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  const formatSegmentTime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    const milliseconds = Math.round((seconds % 1) * 1000)
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}:${milliseconds.toString().padStart(3, '0')}`
  }

  // Redirect logic - use independent useEffect
  useEffect(() => {
    if (!authLoading && !user) {
      // Delay redirect to avoid React rendering conflicts
      const timeoutId = setTimeout(() => {
        router.replace('/auth')
      }, 100)
      
      return () => clearTimeout(timeoutId)
    }
  }, [user, authLoading, router])

  // Optimize recording data conversion with useMemo
  const recordings = useMemo(() => {
    const converted = sessions.map(session => {
      // Find transcription content and AI summary for this session
      const transcription = session.transcriptions?.[0]
      const aiSummary = session.ai_summaries?.[0]
      
      const recording = {
        id: session.id,
        timestamp: new Date(session.created_at).toLocaleString('zh-CN'),
        duration: formatDuration(session.duration_seconds || 0),
        transcript: transcription?.content || '',
        aiSummary: aiSummary?.summary || '',
        aiTitle: session.title || 'New Recording',
        status: session.status,
        templateId: session.template_id || undefined
      }
      
      return recording
    })
    
    return converted
  }, [sessions])

  // Get selected session
  const selectedSession = useMemo(() => {
    return sessions.find(s => s.id === selectedSessionId)
  }, [sessions, selectedSessionId])

  // Parse timestamp to extract start and end time in seconds
  const parseTimestamp = (timestamp: string) => {
    // If it's design document format [HH:MM:SS:mmm,HH:MM:SS:mmm], parse to seconds
    if (timestamp.startsWith('[') && timestamp.includes(',')) {
      const timeRange = timestamp.slice(1, -1) // Remove brackets
      const [startStr, endStr] = timeRange.split(',')
      
      const parseTimeString = (timeStr: string) => {
        const parts = timeStr.split(':')
        if (parts.length >= 4) {
          const hours = parseInt(parts[0]) || 0
          const minutes = parseInt(parts[1]) || 0
          const seconds = parseInt(parts[2]) || 0
          const milliseconds = parseInt(parts[3]) || 0
          return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
        } else if (parts.length >= 3) {
          const hours = parseInt(parts[0]) || 0
          const minutes = parseInt(parts[1]) || 0
          const seconds = parseInt(parts[2]) || 0
          return hours * 3600 + minutes * 60 + seconds
        }
        return 0
      }
      
      return {
        start_time: parseTimeString(startStr),
        end_time: parseTimeString(endStr)
      }
    }
    // If not time range format, return default values
    return { start_time: 0, end_time: 0 }
  }

  // Handle retranscription
  const handleRetranscribe = useCallback(async () => {
    if (!selectedSessionId) {
      toast.error('Please select a session first')
      return
    }

    const selectedSession = sessions.find(s => s.id === selectedSessionId)
    if (!selectedSession) {
      toast.error('Session does not exist')
      return
    }

    if (selectedSession.status !== 'completed') {
      toast.error('Only completed sessions can be retranscribed')
      return
    }

    try {
      // Save current selected session ID to prevent loss during retranscription
      const retranscribeSessionId = selectedSessionId
      
      // Set retranscription state and show overlay
      setIsRetranscribing(true)
      setHasSeenProcessing(false)
      
      // Record current transcription signature as baseline
      if (selectedSession?.transcriptions && selectedSession.transcriptions.length > 0) {
        const t = selectedSession.transcriptions[0] as unknown as { id?: string; content?: string; segments?: unknown }
        const segmentsLength = Array.isArray(t?.segments)
          ? (t?.segments as unknown[]).length
          : typeof t?.segments === 'string'
            ? (t?.segments as string).length
            : 0
        setRetranscribeBaseline({
          id: t?.id,
          contentLength: t?.content ? t.content.length : 0,
          segmentsLength
        })
      } else {
        setRetranscribeBaseline({ id: undefined, contentLength: 0, segmentsLength: 0 })
      }
      
      toast.info('Retranscribing, please wait...', { duration: 2000 })
      
      // Add brief delay to ensure overlay is visible
      await new Promise(resolve => setTimeout(resolve, 300))
      
      // Call retranscription API
      if (!apiClient) {
        throw new Error('API client not initialized')
      }

      const response = await apiClient.retranscribeSession(retranscribeSessionId)

      if (!response.success) {
        throw new Error(response.message || 'Retranscription request failed')
      }

      toast.success('Retranscription started, please wait for completion')
      
      // Refresh session list to get latest status
      await fetchSessions()
      
      // Ensure selected session remains valid after refresh
      setTimeout(() => {
        if (selectedSessionId !== retranscribeSessionId) {
          setSelectedSessionId(retranscribeSessionId)
        }
      }, 100)
      
      // Fallback: only close overlay on timeout, not on completed status
      const startTs = Date.now()
      const fallbackCheck = () => {
        if (!isRetranscribingRef.current) return
        
        if (Date.now() - startTs > 8000) {
          setIsRetranscribing(false)
          setHasSeenProcessing(false)
          setRetranscribeBaseline(null)
          setForceHideRetranscribeOverlay(true)
          return
        }
        setTimeout(fallbackCheck, 500)
      }
      setTimeout(fallbackCheck, 2000)
      
    } catch (error: unknown) {
      const err = error as { response?: { status?: number }; message?: string }
      console.error('Retranscription failed:', error)
      
      // Reset state on failure
      setIsRetranscribing(false)
      setHasSeenProcessing(false)
      
      if (err.response?.status === 404 || err.message?.includes('404')) {
        toast.warning('Retranscription feature temporarily unavailable, please try again later')
      } else {
        toast.error(`Retranscription failed: ${err.message}`)
      }
      setRetranscribeBaseline(null)
    }
  }, [selectedSessionId, sessions, apiClient, fetchSessions])

  // Handle transcript update for editing
  const handleTranscriptUpdate = useCallback(async (updatedTranscript: TranscriptItem[]) => {
    setCurrentTranscript(updatedTranscript)
    
    // Update the full transcript text as well
    const updatedText = updatedTranscript.map(item => item.text).join(' ')
    setFullTranscriptText(updatedText)
    
    // Save to backend
    try {
      // Prefer selectedSessionId, fallback to currentRecordingSessionId
      const sessionId = selectedSessionId || currentRecordingSessionId
      
      if (sessionId) {
        // Try to find corresponding session from sessions state
        let session = sessions.find(s => s.id === sessionId)
        let currentTranscriptionId = ''
        let originalSegments: unknown[] = []
        
        if (session && session.transcriptions && session.transcriptions.length > 0) {
          // Get transcription info from sessions state
          currentTranscriptionId = session.transcriptions[0].id
          originalSegments = session.transcriptions[0].segments || []
        } else if (transcriptionId) {
          // Use global transcriptionId if not found in sessions state
          currentTranscriptionId = transcriptionId
          originalSegments = []
        } else {
          // Last attempt: refresh sessions data if transcription record exists but sessions not updated
          await fetchSessions()
          
          // Re-find session
          const refreshedSessions = sessions
          session = refreshedSessions.find(s => s.id === sessionId)
          
          if (session && session.transcriptions && session.transcriptions.length > 0) {
            currentTranscriptionId = session.transcriptions[0].id
            originalSegments = session.transcriptions[0].segments || []
          } else {
            toast.warning('Transcription data is syncing, please try again later')
            return
          }
        }
        
        // Handle possible string format segments
        if (typeof originalSegments === 'string') {
          try {
            originalSegments = JSON.parse(originalSegments)
          } catch (error) {
            console.error('Failed to parse original segments:', error)
            originalSegments = []
          }
        }
        
        // Convert transcript items to segments format, preserving original timing data
        const segments = updatedTranscript.map((item, index) => {
          // Try to find matching original segment by index or content
          const originalSegment = (originalSegments[index] || {}) as {
            speaker?: string
            start_time?: number
            end_time?: number
            confidence_score?: number | null
            is_final?: boolean
          }
          
          // Parse timing from timestamp if available, otherwise use original timing
          const { start_time, end_time } = parseTimestamp(item.timestamp)
          
          return {
            index: index + 1,
            speaker: item.speaker || originalSegment.speaker || 'unknown',
            start_time: start_time || originalSegment.start_time || 0,
            end_time: end_time || originalSegment.end_time || 0,
            text: item.text,
            confidence_score: originalSegment.confidence_score || null,
            is_final: originalSegment.is_final !== undefined ? originalSegment.is_final : true
          }
        })
        
        // Call API to update transcription
        const supabaseModule = await import('@/lib/supabase')
        const token = supabaseModule.supabase ? (await supabaseModule.supabase.auth.getSession()).data.session?.access_token : null
        
        if (token) {
          const apiClient = new supabaseModule.APIClient(
            '/api/v1',
            () => token
          )
        
          await apiClient.updateTranscription(currentTranscriptionId, segments)
          toast.success('Transcription content saved to server')
          
          // Refresh sessions to get updated data
          fetchSessions()
        } else {
          toast.error('User not logged in, unable to save to server')
        }
      } else {
        toast.warning('No session selected, only local update')
      }
    } catch (error) {
      console.error('Failed to save transcription update:', error)
      toast.error('Failed to save transcription update')
    }
  }, [selectedSessionId, currentRecordingSessionId, sessions, fetchSessions, transcriptionId])

  // Add state tracking for retranscription
  const [isRetranscribing, setIsRetranscribing] = useState(false)
  const [hasSeenProcessing, setHasSeenProcessing] = useState(false)
  // Retranscription baseline: record transcription signature when retranscription starts for comparison
  const [retranscribeBaseline, setRetranscribeBaseline] = useState<{ id?: string; contentLength: number; segmentsLength: number } | null>(null)
  // Force hide overlay (fallback)
  const [forceHideRetranscribeOverlay, setForceHideRetranscribeOverlay] = useState(false)
  // Use refs to get latest sessions and flags in async callbacks
  const sessionsRef = useRef(sessions)
  const isRetranscribingRef = useRef(isRetranscribing)

  useEffect(() => { sessionsRef.current = sessions }, [sessions])
  useEffect(() => { isRetranscribingRef.current = isRetranscribing }, [isRetranscribing])
  
  // Listen for retranscription completion events
  useEffect(() => {
    const handleRetranscriptionCompleted = (event: CustomEvent) => {
      const { sessionId } = event.detail
      
      // If it's the currently selected session, force refresh data and update transcription content
      if (sessionId === selectedSessionId) {
        // Immediately refresh session data
        fetchSessions()
        
        // Delay and refresh again to ensure complete data sync
        setTimeout(() => {
          fetchSessions()
          
          // Force set state to trigger transcription content update
          setIsRetranscribing(false)
          setHasSeenProcessing(false)
          setRetranscribeBaseline(null)
          
          // Force clear current transcription content to trigger reload
          setCurrentTranscript([])
          
          toast.success('Speaker recognition completed! Transcription content updated', {
            duration: 3000
          })
        }, 1000)
      }
    }
    
    window.addEventListener('retranscriptionCompleted', handleRetranscriptionCompleted as EventListener)
    
    return () => {
      window.removeEventListener('retranscriptionCompleted', handleRetranscriptionCompleted as EventListener)
    }
  }, [selectedSessionId, fetchSessions])

  // Listen for selected session status changes, auto-refresh transcription content
  useEffect(() => {
    if (!selectedSessionId) return
    
    const selectedSession = sessions.find(s => s.id === selectedSessionId)
    if (!selectedSession) {
      return
    }
    
    // Track if we've seen processing status
    if (selectedSession.status === 'processing' && isRetranscribing && !hasSeenProcessing) {
      setHasSeenProcessing(true)
    }
    
    // Check if transcription content needs updating (retranscription completed or first load)
    let shouldUpdateTranscript = false
    let justCompletedRetranscription = false
    
    // Retranscription completion detection: only reset after seeing processing then completed
    if (isRetranscribing && hasSeenProcessing && selectedSession.status === 'completed') {
      setIsRetranscribing(false)
      setHasSeenProcessing(false)
      shouldUpdateTranscript = true
      justCompletedRetranscription = true
      toast.success('Transcription reprocessing completed!', {
        duration: 4000
      })
    }

    // Supplementary completion detection: if we couldn't catch processing status but transcription content changed compared to baseline
    if (isRetranscribing && selectedSession.status === 'completed') {
      const t = selectedSession.transcriptions && selectedSession.transcriptions.length > 0
        ? (selectedSession.transcriptions[0] as unknown as { id?: string; content?: string; segments?: unknown })
        : undefined
      const currentSignature = {
        id: t?.id,
        contentLength: t?.content ? t.content.length : 0,
        segmentsLength: Array.isArray(t?.segments)
          ? (t?.segments as unknown[]).length
          : typeof t?.segments === 'string'
            ? (t?.segments as string).length
            : 0
      }
      
      if (retranscribeBaseline && (
        currentSignature.id !== retranscribeBaseline.id ||
        currentSignature.contentLength !== retranscribeBaseline.contentLength ||
        currentSignature.segmentsLength !== retranscribeBaseline.segmentsLength
      )) {
        setIsRetranscribing(false)
        setHasSeenProcessing(false)
        setRetranscribeBaseline(null)
        shouldUpdateTranscript = true
        justCompletedRetranscription = true
        toast.success('Transcription reprocessing completed!', { duration: 4000 })
      }
    }
    
    // Transcription content loading conditions: first load, retranscription completed, or current content is empty
    if (selectedSession.status === 'completed' && 
        selectedSession.transcriptions && 
        selectedSession.transcriptions.length > 0 &&
        (currentTranscript.length === 0 || shouldUpdateTranscript)) {
      
      const transcription = selectedSession.transcriptions[0]
      
      // Rebuild transcription interface data
      if (transcription.segments && Array.isArray(transcription.segments) && transcription.segments.length > 0) {
        const transcriptItems = transcription.segments.map((segment: unknown, index: number) => {
          const segmentData = segment as { 
            start_time?: number
            end_time?: number
            speaker?: string
            text?: string
          }
          return {
            id: `${transcription.id}_segment_${index}`,
            timestamp: segmentData.start_time && segmentData.end_time 
              ? formatSegmentTimeRange(segmentData.start_time, segmentData.end_time)
              : new Date().toLocaleTimeString('zh-CN', { hour12: false }),
            speaker: segmentData.speaker || 'unknown',
            text: segmentData.text || ''
          }
        }).filter((item: { text: string }) => item.text.trim().length > 0)
        
        setCurrentTranscript(transcriptItems)
        setFullTranscriptText(transcription.content || '')
        
        // If retranscription completed, show additional user notification
        if (justCompletedRetranscription) {
          const uniqueSpeakers = Array.from(new Set(transcriptItems.map(item => item.speaker))).filter(s => s !== 'unknown')
          if (uniqueSpeakers.length > 1) {
            toast.success(`Speaker recognition completed! Identified ${uniqueSpeakers.length} speakers`, {
              duration: 3000
            })
          }
        }
      }
    }
    
    // If session status is not completed or processing, reset retranscription state
    if (selectedSession.status !== 'completed' && selectedSession.status !== 'processing') {
      setIsRetranscribing(false)
      setHasSeenProcessing(false)
      setRetranscribeBaseline(null)
    }
  }, [sessions, selectedSessionId, currentTranscript.length, isRetranscribing, hasSeenProcessing, retranscribeBaseline])

  // Format segment time range for display
  const formatSegmentTimeRange = (startTime: number, endTime: number) => {
    const formatTime = (seconds: number) => {
      const hours = Math.floor(seconds / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      const secs = Math.floor(seconds % 60)
      const milliseconds = Math.floor((seconds % 1) * 1000)
      return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}:${milliseconds.toString().padStart(3, '0')}`
    }
    
    return `[${formatTime(startTime)},${formatTime(endTime)}]`
  }

  // Handle speaker rename
  const handleSpeakerRename = useCallback(async (oldSpeaker: string, newSpeaker: string) => {
    try {
      const sessionId = selectedSessionId || currentRecordingSessionId
      if (!sessionId) {
        toast.error('Unable to rename speaker: invalid session')
        return
      }

      // Get authentication token
      const supabaseModule = await import('@/lib/supabase')
      const token = supabaseModule.supabase ? (await supabaseModule.supabase.auth.getSession()).data.session?.access_token : null
      
      if (!token) {
        toast.error('Unable to rename speaker: authentication failed')
        return
      }

      // Use unified API client to update speaker name
      httpClient.setAuthTokenGetter(() => token)
      const result = await apiPost('api', `/v1/sessions/${sessionId}/rename-speaker`, {
        oldSpeaker,
        newSpeaker
      }) as RenameSpeakerResponse
      
      if (result.success) {
        toast.success(`Speaker renamed: ${oldSpeaker} → ${newSpeaker}`)
        
        // Immediately update speaker names in current transcript content
        if (currentTranscript.length > 0) {
          const updatedTranscript = currentTranscript.map(item => ({
            ...item,
            speaker: item.speaker === oldSpeaker ? newSpeaker : item.speaker
          }))
          setCurrentTranscript(updatedTranscript)
        }
        
        // Multiple refreshes to ensure data sync, similar to retranscription handling
        await handleRefreshSessions()
        
        // Refresh again after 1 second to ensure complete data sync
        setTimeout(async () => {
          await handleRefreshSessions()
          
          // Re-process selected session transcription data to ensure complete UI update
          const refreshedSessions = sessions.find(s => s.id === sessionId)
          if (refreshedSessions) {
            await processSessionData(refreshedSessions)
          }
        }, 1000)
        
        // Final refresh after 3 seconds to ensure all data is synced
        setTimeout(async () => {
          await handleRefreshSessions()
        }, 2000)
        
      } else {
        throw new Error(result.message || 'Speaker rename failed')
      }
    } catch (error) {
      console.error('Failed to rename speaker:', error)
      toast.error(`Failed to rename speaker: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }, [selectedSessionId, currentRecordingSessionId, handleRefreshSessions, currentTranscript, sessions, processSessionData])

  // Show loading interface if loading or not logged in
  if (authLoading || !user) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-100">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  const renderMainContent = () => {
    switch (currentView) {
      case 'record':
        return (
          <div className="flex-1 flex h-full">
            <FileList 
              recordings={recordings}
              selectedId={selectedSessionId}
              onSelect={handleSessionSelect}
              onDelete={handleDeleteSession}
              onTranscript={handleTranscript}
              onRecordingStateChange={handleRecordingStateChange}
              onSessionCreated={handleSessionCreated}
              onTemplateSelect={handleTemplateSelect}
              isRecording={isRecording}
            />
            <div className="flex-1 flex flex-col min-h-0">
              <Header
                isRecording={isRecording}
                onAISummary={handleAISummary}
                isLoadingSummary={isLoadingSummary}
                sessionId={selectedSessionId}
                onAudioTimeUpdate={handleAudioTimeUpdate}
                onAudioSeekTo={handleSeekToTime}
                onRefreshSessions={handleRefreshSessions}
                onRefreshAudio={refreshAudioRef}
                apiClient={apiClient}
              />
              <div className="flex flex-1 min-h-0">
                <div className={`${showAISummaryPanel ? 'w-1/3' : 'flex-1'} flex-shrink-0`}>
                  <TranscriptView
                    transcript={currentTranscript}
                    timestamp={selectedSession?.created_at 
                      ? new Date(selectedSession.created_at).toLocaleString('zh-CN') 
                      : new Date().toLocaleString('zh-CN')}
                    isRecording={isRecording}
                    onTranscriptUpdate={handleTranscriptUpdate}
                    currentPlaybackTime={currentAudioTime}
                    onSeekToTime={handleSeekToTime}
                    title={selectedSession?.title || (isRecording ? "录音中..." : "新建录音")}
                    sessionStatus={selectedSession?.status}
                    onRetranscribe={handleRetranscribe}
                    onSpeakerRename={handleSpeakerRename}
                  />
                </div>
                <AISummaryPanel
                  isVisible={showAISummaryPanel}
                  onClose={() => setShowAISummaryPanel(false)}
                  sessionId={selectedSessionId}
                  transcription={fullTranscriptText || currentTranscript.map(t => t.text).join(' ')}
                  summary={aiSummary}
                  title={aiTitle}
                  isLoading={isLoadingSummary}
                  onSummaryUpdate={handleSummaryUpdate}
                  onTitleUpdate={handleTitleUpdate}
                  summaryId={aiSummaryId}
                  transcriptionId={transcriptionId}
                  onRefreshSessions={handleRefreshSessions}
                  onGenerateSummary={handleAISummary}
                />
              </div>
            </div>
          </div>
        )
      case 'templates':
        return (
          <div className="flex-1 p-6 bg-white overflow-auto">
            <TemplateManager />
          </div>
        )
      case 'ai':
        return (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <h2 className="text-2xl font-bold text-gray-900 mb-4">AI 助手</h2>
              <p className="text-gray-600">AI 功能开发中...</p>
            </div>
          </div>
        )
      default:
        return null
    }
  }

  return (
    <div className="h-screen flex bg-gray-100 overflow-hidden">
      <Sidebar 
        currentView={currentView}
        onViewChange={setCurrentView}
        user={user}
      />
      {renderMainContent()}

      {/* Processing Overlay - Full screen overlay during retranscription processing */}
      {(selectedSession?.status === 'processing' || (isRetranscribing && !forceHideRetranscribeOverlay)) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 max-w-md w-full mx-4 text-center">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Retranscribing
            </h3>
            <p className="text-gray-600 mb-4">
              Re-identifying speakers and transcribing content, this may take a few minutes
            </p>
            <div className="space-y-3">
              <div className="flex items-center justify-center space-x-2 text-sm text-gray-500">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
                <span>Processing...</span>
              </div>
              <p className="text-xs text-gray-400">
                Please do not close the page or perform other operations
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
} 