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
    
    // Simplified: rely on real-time subscription INSERT/UPDATE events for auto-update
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

  // 新的AI总结处理函数
  const handleAISummary = useCallback(async (templateId?: string) => {
    console.log('🔍 handleAISummary调试:', { 
      userId: user?.id, 
      sessionId: selectedSessionId || currentRecordingSessionId, 
      templateId,
      templateIdType: typeof templateId,
      isTemplateIdString: typeof templateId === 'string'
    })
    
    if (!fullTranscriptText && currentTranscript.length === 0) {
      toast.error('No transcription content available, cannot generate summary')
      return
    }

    const transcriptText = fullTranscriptText || currentTranscript.map(t => t.text).join(' ')
    
    if (!transcriptText.trim()) {
      toast.error('Transcription content is empty, cannot generate summary')
      return
    }

    // 确保有有效的会话ID
    const sessionId = selectedSessionId || currentRecordingSessionId
    if (!sessionId) {
      toast.error('Cannot find valid recording session, please select a recording first')
      return
    }

    // 如果没有传入templateId，使用会话选择的模板
    let finalTemplateId = templateId
    if (!finalTemplateId) {
      const currentSession = sessions.find(s => s.id === sessionId)
      if (!currentSession) {
        toast.error('Cannot find corresponding recording session, unable to generate summary')
        return
      }
      // 注意：RecordingSession中暂时没有模板ID字段，使用默认模板
      finalTemplateId = '' // 使用默认模板
    }
    
    console.log('🎯 使用的模板ID:', finalTemplateId)

    console.log('🤖 开始生成AI总结，转录内容长度:', transcriptText.length)
    setShowAISummaryPanel(true)
    setIsLoadingSummary(true)

    try {
      // 自动开始生成AI总结，使用指定的模板
      const summaryResult = await generateSummary(sessionId, transcriptText, finalTemplateId)
      if (summaryResult) {
        console.log('🔄 设置新的AI总结内容:', summaryResult.summary.length, '字符')
        setAiSummary(summaryResult.summary)
        
        // 从刷新后的会话数据中获取AI总结ID
        const refreshedSession = sessions.find(s => s.id === sessionId)
        if (refreshedSession?.ai_summaries && refreshedSession.ai_summaries.length > 0) {
          const latestSummary = refreshedSession.ai_summaries[0]
          setAiSummaryId(latestSummary.id)
        }
        
        // 生成总结成功后，继续生成标题
        const titleResult = await generateTitle(sessionId, transcriptText, summaryResult.summary)
        if (titleResult) {
          setAiTitle(titleResult.title)
        }
        
        toast.success('AI summary and title generation completed')
      }
    } catch (error) {
      console.error('生成AI总结失败:', error)
      toast.error('Failed to generate AI summary')
    } finally {
      setIsLoadingSummary(false)
    }
  }, [fullTranscriptText, currentTranscript, selectedSessionId, currentRecordingSessionId, generateSummary, generateTitle, user?.id, sessions])

  // 处理模板选择
  const handleTemplateSelect = useCallback(async (sessionId: string, templateId: string) => {
    console.log('🎨 模板选择处理:', { sessionId, templateId })
    
    try {
      // 更新会话的模板选择
      if (apiClient) {
        await apiClient.updateSessionTemplate(sessionId, templateId)
        console.log('✅ 会话模板已更新到服务器')
        
        // 刷新会话数据
        await fetchSessions()
        toast.success('模板选择已保存')
      } else {
        console.error('❌ API客户端未初始化')
        toast.error('无法保存模板选择')
      }
    } catch (error) {
      console.error('更新会话模板失败:', error)
      toast.error('保存模板选择失败')
    }
  }, [apiClient, fetchSessions])

  // 处理删除录音会话
  const handleDeleteSession = useCallback(async (sessionId: string) => {
    if (window.confirm('确定要删除这条录音记录吗？此操作不可撤销。')) {
      try {
        await deleteSession(sessionId)
        // 如果删除的是当前选中的会话，清除选中状态和音频播放器状态
        if (selectedSessionId === sessionId) {
          setSelectedSessionId('')
          setCurrentTranscript([])
          setFullTranscriptText('')
          setAiSummary('')
          setAiTitle('')
          setAiSummaryId('')
          setTranscriptionId('')
          setShowAISummaryPanel(false)
          
          // 重置音频播放器相关状态
          setCurrentAudioTime(0)
          
          // 如果有全局音频播放器控制，也停止播放
          if (window.audioPlayerSeekTo) {
            try {
              // 尝试停止音频播放（通过seek到0来重置）
              window.audioPlayerSeekTo(0)
            } catch (error) {
              console.log('重置音频播放器时出错:', error)
            }
          }
          
          console.log('🧹 已清除删除会话的所有相关状态')
        }
      } catch (error) {
        console.error('删除会话失败:', error)
        toast.error('删除录音会话失败')
      }
    }
  }, [deleteSession, selectedSessionId])

  // 处理AI总结更新
  const handleSummaryUpdate = useCallback((summary: string) => {
    setAiSummary(summary)
  }, [])

  // 处理AI标题更新
  const handleTitleUpdate = useCallback((title: string) => {
    setAiTitle(title)
  }, [])

  // 处理刷新会话数据
  const handleRefreshSessions = useCallback(() => {
    if (user?.id) {
      console.log('🔄 保存后刷新会话数据')
      fetchSessions()
    }
  }, [user?.id, fetchSessions])

  // 格式化时间戳 - 将秒数转换为 HH:MM:SS:mmm 格式
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

  // 重定向逻辑 - 使用独立的 useEffect
  useEffect(() => {
    if (!authLoading && !user) {
      // 延迟重定向以避免React渲染冲突
      const timeoutId = setTimeout(() => {
        router.replace('/auth')
      }, 100)
      
      return () => clearTimeout(timeoutId)
    }
  }, [user, authLoading, router])

  // 使用 useMemo 优化 recording 数据转换
  const recordings = useMemo(() => {
    console.log('🎯 转换会话数据为录音列表:', {
      sessionsCount: sessions.length,
      selectedSessionId,
      firstFewSessions: sessions.slice(0, 3).map(s => ({ id: s.id, title: s.title, status: s.status }))
    })
    
    const converted = sessions.map(session => {
      // 查找该会话的转录内容和AI总结
      const transcription = session.transcriptions?.[0]
      const aiSummary = session.ai_summaries?.[0]
      
      const recording = {
        id: session.id,
        timestamp: new Date(session.created_at).toLocaleString('zh-CN'),
        duration: formatDuration(session.duration_seconds || 0),
        transcript: transcription?.content || '',
        aiSummary: aiSummary?.summary || '',
        aiTitle: session.title || '新建录音',
        status: session.status,
        templateId: session.template_id || undefined // 使用真实的模板ID
      }
      
      return recording
    })
    
    console.log('📋 转换后的录音列表:', {
      recordingsCount: converted.length,
      firstFewRecordings: converted.slice(0, 3).map(r => ({ 
        id: r.id, 
        title: r.aiTitle, 
        status: r.status,
        hasTranscript: !!r.transcript,
        templateId: r.templateId
      }))
    })
    
    return converted
  }, [sessions, selectedSessionId])

  // 获取选中的会话
  const selectedSession = useMemo(() => {
    return sessions.find(s => s.id === selectedSessionId)
  }, [sessions, selectedSessionId])

  // Parse timestamp to extract start and end time in seconds
  const parseTimestamp = (timestamp: string) => {
    // 如果是设计文档格式 [HH:MM:SS:mmm,HH:MM:SS:mmm]，解析为秒数
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
    // 如果不是时间范围格式，返回默认值
    return { start_time: 0, end_time: 0 }
  }

  // Handle retranscription
  const handleRetranscribe = useCallback(async () => {
    if (!selectedSessionId) {
      toast.error('请先选择一个会话')
      return
    }

    const selectedSession = sessions.find(s => s.id === selectedSessionId)
    if (!selectedSession) {
      toast.error('会话不存在')
      return
    }

    if (selectedSession.status !== 'completed') {
      toast.error('只有已完成的会话才能重新转录')
      return
    }

    try {
      console.log('🔄 开始重新转录会话:', selectedSessionId)
      
      // 保存当前选中的会话ID，防止在重新转录过程中丢失
      const retranscribeSessionId = selectedSessionId
      
      // 立即设置重新转录状态并显示遮罩
      setIsRetranscribing(true)
      setHasSeenProcessing(false) // 重置处理状态标记
      // 记录当前选中会话的转录签名，作为重新转录的基线
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
      
      // 立即显示重新转录的提示
      toast.info('正在重新转录，请稍候...', { duration: 2000 })
      
      // 添加短暂延时，确保遮罩显示给用户看到
      await new Promise(resolve => setTimeout(resolve, 300))
      
      // 调用重新转录API - 使用APIClient的专用方法
      if (!apiClient) {
        throw new Error('API客户端未初始化')
      }

      const response = await apiClient.retranscribeSession(retranscribeSessionId)

      if (!response.success) {
        throw new Error(response.message || '重新转录请求失败')
      }

      console.log('✅ 重新转录请求成功:', response)
      toast.success('重新转录已开始，请等待处理完成')
      
      // 确保在刷新会话数据后保持选中状态
      console.log('🔒 重新转录过程中保持选中会话:', retranscribeSessionId)
      
      // 立即刷新会话列表以获取最新状态
      await fetchSessions()
      
      // 刷新后，确保选中的会话仍然有效（防止被重置）
      setTimeout(() => {
        if (selectedSessionId !== retranscribeSessionId) {
          console.log('🔧 重新转录后恢复选中会话:', retranscribeSessionId)
          setSelectedSessionId(retranscribeSessionId)
        }
      }, 100)
      
      // 兜底：极短音频瞬间完成时可能未经历 processing，这里短轮询最多4秒
      const startTs = Date.now()
      const fallbackCheck = () => {
        if (!isRetranscribingRef.current) return
        const s = sessionsRef.current.find(s => s.id === retranscribeSessionId)
        if (s && s.status === 'completed') {
          console.log('✅ 兜底检测：会话为completed，关闭重新转录遮罩')
          setIsRetranscribing(false)
          setHasSeenProcessing(false)
          setRetranscribeBaseline(null)
          setForceHideRetranscribeOverlay(true)
          return
        }
        if (Date.now() - startTs > 4000) {
          console.log('⏱️ 兜底检测超时，关闭重新转录遮罩')
          setIsRetranscribing(false)
          setHasSeenProcessing(false)
          setRetranscribeBaseline(null)
          setForceHideRetranscribeOverlay(true)
          return
        }
        setTimeout(fallbackCheck, 300)
      }
      setTimeout(fallbackCheck, 400)
      
    } catch (error: unknown) {
      const err = error as { response?: { status?: number }; message?: string }
      console.error('❌ 重新转录失败:', error)
      
      // 重新转录失败时重置状态
      setIsRetranscribing(false)
      setHasSeenProcessing(false)
      
      // 如果是API不存在的错误，我们回退到使用现有逻辑
      if (err.response?.status === 404 || err.message?.includes('404')) {
        console.log('🔄 重新转录API不存在，尝试使用备用方法')
        // 可以在这里添加备用的重新转录逻辑
        toast.warning('重新转录功能暂时不可用，请稍后再试')
      } else {
        toast.error(`重新转录失败: ${err.message}`)
      }
      setRetranscribeBaseline(null)
    }
  }, [selectedSessionId, sessions, apiClient, fetchSessions])

  // Handle transcript update for editing
  const handleTranscriptUpdate = useCallback(async (updatedTranscript: TranscriptItem[]) => {
    console.log('📝 更新转录内容:', updatedTranscript.length, '条记录')
    setCurrentTranscript(updatedTranscript)
    
    // Update the full transcript text as well
    const updatedText = updatedTranscript.map(item => item.text).join(' ')
    setFullTranscriptText(updatedText)
    
    // Save to backend
    try {
      // 优先使用selectedSessionId，如果没有则使用currentRecordingSessionId
      const sessionId = selectedSessionId || currentRecordingSessionId
      
      if (sessionId) {
        console.log('📍 保存转录更新，使用会话ID:', sessionId)
        
        // 首先尝试从sessions状态中找到对应的会话
        let session = sessions.find(s => s.id === sessionId)
        let currentTranscriptionId = ''
        let originalSegments: unknown[] = []
        
        if (session && session.transcriptions && session.transcriptions.length > 0) {
          // 从sessions状态中获取转录信息
          currentTranscriptionId = session.transcriptions[0].id
          originalSegments = session.transcriptions[0].segments || []
          console.log('✅ 从sessions状态中找到转录记录:', currentTranscriptionId)
        } else if (transcriptionId) {
          // 如果sessions状态中没有，但有全局的transcriptionId变量，使用它
          console.log('⚠️ sessions状态中未找到转录记录，使用全局transcriptionId:', transcriptionId)
          currentTranscriptionId = transcriptionId
          originalSegments = [] // 没有原始segments数据
        } else {
          // 最后尝试：如果是刚转录完成的会话，可能转录记录已经存在但sessions还没更新
          console.log('🔄 sessions状态可能未同步，尝试刷新后重试...')
          
          // 立即刷新sessions数据
          await fetchSessions()
          
          // 重新查找会话
          const refreshedSessions = sessions
          session = refreshedSessions.find(s => s.id === sessionId)
          
          if (session && session.transcriptions && session.transcriptions.length > 0) {
            currentTranscriptionId = session.transcriptions[0].id
            originalSegments = session.transcriptions[0].segments || []
            console.log('✅ 刷新后找到转录记录:', currentTranscriptionId)
          } else {
            console.log('❌ 刷新后仍未找到转录记录，可能数据还未同步完成')
            toast.warning('转录数据正在同步中，请稍后再试')
            return
          }
        }
        
        console.log('💾 保存转录更新到服务器:', currentTranscriptionId)
        
        // 处理可能的字符串格式的segments
        if (typeof originalSegments === 'string') {
          try {
            originalSegments = JSON.parse(originalSegments)
          } catch (error) {
            console.error('解析原始segments失败:', error)
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
        
        console.log('🕒 构建的segments数据:', segments.map(s => ({ 
          index: s.index, 
          start_time: s.start_time, 
          end_time: s.end_time, 
          text: s.text.substring(0, 50) + '...' 
        })))
        
        // Call API to update transcription
        const supabaseModule = await import('@/lib/supabase')
        const token = supabaseModule.supabase ? (await supabaseModule.supabase.auth.getSession()).data.session?.access_token : null
        
                  if (token) {
            const apiClient = new supabaseModule.APIClient(
              '/api/v1',
              () => token
            )
          
          await apiClient.updateTranscription(currentTranscriptionId, segments)
          toast.success('转录内容已保存到服务器')
          
          // Refresh sessions to get updated data
          fetchSessions()
        } else {
          toast.error('用户未登录，无法保存到服务器')
        }
      } else {
        toast.warning('未选择会话，仅在本地更新')
      }
    } catch (error) {
      console.error('保存转录更新失败:', error)
      toast.error('保存转录更新失败')
    }
  }, [selectedSessionId, currentRecordingSessionId, sessions, fetchSessions, transcriptionId])

  // 添加状态跟踪是否正在重新转录
  const [isRetranscribing, setIsRetranscribing] = useState(false)
  const [hasSeenProcessing, setHasSeenProcessing] = useState(false)
  // 重新转录基线：记录发起重新转录时的转录签名，用于后续比对
  const [retranscribeBaseline, setRetranscribeBaseline] = useState<{ id?: string; contentLength: number; segmentsLength: number } | null>(null)
  // 强制隐藏遮罩（兜底）
  const [forceHideRetranscribeOverlay, setForceHideRetranscribeOverlay] = useState(false)
  // 引入refs以便在异步回调中拿到最新的sessions与标志位
  const sessionsRef = useRef(sessions)
  const isRetranscribingRef = useRef(isRetranscribing)

  useEffect(() => { sessionsRef.current = sessions }, [sessions])
  useEffect(() => { isRetranscribingRef.current = isRetranscribing }, [isRetranscribing])
  
  // 监听选中会话的状态变化，自动刷新转录内容
  useEffect(() => {
    if (!selectedSessionId) return
    
    const selectedSession = sessions.find(s => s.id === selectedSessionId)
    if (!selectedSession) {
      console.log('⚠️ 监听状态变化时未找到选中会话:', selectedSessionId)
      return
    }
    
    // 跟踪是否看到过 processing 状态
    if (selectedSession.status === 'processing' && isRetranscribing && !hasSeenProcessing) {
      setHasSeenProcessing(true)
      
      // 设置定时检查，防止状态变化被遗漏
      // const checkInterval = setInterval(async () => {
      //   await fetchSessions()
      // }, 1000) // 每秒检查一次
      
      // // 10秒后清除定时器
      // setTimeout(() => {
      //   clearInterval(checkInterval)
      // }, 10000)
    }
    
    // 重新转录完成检测：只有在看到 processing 后变为 completed 才重置
    if (isRetranscribing && hasSeenProcessing && selectedSession.status === 'completed') {
      setIsRetranscribing(false)
      setHasSeenProcessing(false)
      toast.success('转录重新处理完成！', {
        duration: 4000
      })
    }

    // 补充完成检测：如果未能捕获到processing状态，但转录内容与基线相比发生变化，则视为完成
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
        toast.success('转录重新处理完成！', { duration: 4000 })
      }
    }
    
    // 正常的转录内容加载（首次加载或切换会话）
    if (selectedSession.status === 'completed' && 
        selectedSession.transcriptions && 
        selectedSession.transcriptions.length > 0 &&
        currentTranscript.length === 0) {
      
      const transcription = selectedSession.transcriptions[0]
      
      // 重新构建转录界面数据（简化版，不涉及重新转录检测）
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
      }
    }
    
    // 如果会话状态不是completed或processing，重置重新转录状态
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
        console.error('❌ 无法重命名说话人: 没有有效的会话ID')
        toast.error('无法重命名说话人: 会话无效')
        return
      }

      console.log('🎭 重命名说话人:', { sessionId, oldSpeaker, newSpeaker })

      // Get authentication token
      const supabaseModule = await import('@/lib/supabase')
      const token = supabaseModule.supabase ? (await supabaseModule.supabase.auth.getSession()).data.session?.access_token : null
      
      if (!token) {
        console.error('❌ 无法重命名说话人: 缺少认证令牌')
        toast.error('无法重命名说话人: 认证失败')
        return
      }

      // 使用统一API客户端更新说话人名称
      httpClient.setAuthTokenGetter(() => token)
      const result = await apiPost('api', `/v1/sessions/${sessionId}/rename-speaker`, {
        oldSpeaker,
        newSpeaker
      }) as RenameSpeakerResponse
      
      if (result.success) {
        console.log('✅ 说话人重命名成功')
        toast.success(`说话人已重命名: ${oldSpeaker} → ${newSpeaker}`)
        
        // 立即更新当前转录内容中的说话人名称
        if (currentTranscript.length > 0) {
          console.log('🔄 立即更新界面中的说话人名称')
          const updatedTranscript = currentTranscript.map(item => ({
            ...item,
            speaker: item.speaker === oldSpeaker ? newSpeaker : item.speaker
          }))
          setCurrentTranscript(updatedTranscript)
        }
        
        // 多次刷新确保数据同步，类似重新转录的处理方式
        // 立即刷新第一次
        await handleRefreshSessions()
        
        // 1秒后再刷新一次，确保数据完全同步
        setTimeout(async () => {
          await handleRefreshSessions()
          
          // 重新处理选中会话的转录数据，确保界面完全更新
          const refreshedSessions = sessions.find(s => s.id === sessionId)
          if (refreshedSessions) {
            await processSessionData(refreshedSessions)
          }
        }, 1000)
        
        // 3秒后最后一次刷新，确保所有数据都已同步
        setTimeout(async () => {
          await handleRefreshSessions()
        }, 2000)
        
      } else {
        throw new Error(result.message || '重命名说话人失败')
      }
    } catch (error) {
      console.error('❌ 重命名说话人失败:', error)
      toast.error(`重命名说话人失败: ${error instanceof Error ? error.message : '未知错误'}`)
    }
  }, [selectedSessionId, currentRecordingSessionId, handleRefreshSessions, currentTranscript, sessions, processSessionData])

  // 如果正在加载或未登录，显示加载界面
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

      {/* Processing Overlay - 重新转录处理期间的全屏遮罩 */}
      {(selectedSession?.status === 'processing' || (isRetranscribing && !forceHideRetranscribeOverlay)) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 max-w-md w-full mx-4 text-center">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              正在重新转录
            </h3>
            <p className="text-gray-600 mb-4">
              正在重新识别说话人和转录内容，这可能需要几分钟时间
            </p>
            <div className="space-y-3">
              <div className="flex items-center justify-center space-x-2 text-sm text-gray-500">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
                <span>处理中...</span>
              </div>
              <p className="text-xs text-gray-400">
                请勿关闭页面或进行其他操作
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
} 