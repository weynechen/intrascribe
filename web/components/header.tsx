'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { MessageSquare, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AudioPlayer } from './audio-player'
import { useAuth } from '@/hooks/useAuth'
import { apiGet, httpClient } from '@/lib/api-client'
import { toast } from 'sonner'

interface BatchTranscriptionStatistics {
  speaker_count: number
  total_segments: number
  total_duration_seconds: number
  transcription_length: number
}

interface BatchTranscriptionResponse {
  status: string
  statistics?: BatchTranscriptionStatistics
}

interface AudioFile {
  public_url: string
  id?: string
  name?: string
}

interface HeaderProps {
  isRecording: boolean
  onAISummary?: () => void
  isLoadingSummary?: boolean
  sessionId?: string
  onAudioTimeUpdate?: (currentTime: number) => void
  onAudioSeekTo?: (time: number) => void
  onRefreshSessions?: () => void
  onRefreshAudio?: React.MutableRefObject<(() => Promise<void>) | null>
  apiClient?: unknown
}

export function Header({ 
  isRecording, 
  onAISummary,
  isLoadingSummary = false,
  sessionId,
  onAudioTimeUpdate,
  onAudioSeekTo,
  onRefreshSessions,
  onRefreshAudio,
  apiClient
}: HeaderProps) {
  const [audioUrl, setAudioUrl] = useState<string>()
  const [hasAudio, setHasAudio] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const { session } = useAuth()
  const wasRecordingRef = useRef(isRecording)

  // Check if session has audio files
  const checkSessionAudio = useCallback(async (sessionId: string) => {
    try {
      if (!sessionId) {
        return
      }

      // Use unified API client to get audio files
      httpClient.setAuthTokenGetter(() => session?.access_token || null)
      
      const data = await apiGet('api', `/v1/sessions/${sessionId}/audio_files`) as AudioFile[]
        
      if (data && data.length > 0) {
        const audioFile = data[0] // Take first audio file
        // Convert original URL to proxy-accessed URL
        const originalUrl = audioFile.public_url
        let proxyUrl = originalUrl
        
        // If HTTP address, convert to proxy path
        //TODO: Legacy code, can be removed later
        if (originalUrl && originalUrl.startsWith('http://localhost:54321/')) {
          proxyUrl = originalUrl.replace('http://localhost:54321/', '/')
        } else if (originalUrl && originalUrl.includes('localhost:54321')) {
          // Handle other possible formats
          proxyUrl = originalUrl.replace(/https?:\/\/[^/]*localhost:54321\//, '/')
        }
        
        setAudioUrl(proxyUrl)
        setHasAudio(true)
      } else {
        setHasAudio(false)
        setAudioUrl(undefined)
      }
    } catch (error) {
      setHasAudio(false)
      setAudioUrl(undefined)
    }
  }, [session?.access_token])

  // Handle audio file import
  const handleAudioImport = () => {
    if (isRecording) {
      toast.warning('Recording in progress, cannot import audio files')
      return
    }
    
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  // Handle file selection
  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (!files || files.length === 0) return

    const selectedFiles = Array.from(files)

    // Check file formats
    const validFiles = selectedFiles.filter(file => {
      const fileName = file.name.toLowerCase()
      const isWav = fileName.endsWith('.wav') || file.type === 'audio/wav' || file.type === 'audio/x-wav'
      const isMp3 = fileName.endsWith('.mp3') || file.type === 'audio/mpeg' || file.type === 'audio/mp3'
      const isValidFormat = isWav || isMp3
      
      if (!isValidFormat) {
        toast.error(`File ${file.name} format not supported, only WAV and MP3 formats are supported`)
      } else {
      }
      return isValidFormat
    })

    if (validFiles.length === 0) {
      toast.error('No valid audio files')
      return
    }

    if (validFiles.length > 1) {
      toast.error('Currently only supports single file import')
      return
    }

    const file = validFiles[0]
    await processBatchTranscription(file)
    
    // Clear input value for next selection
    event.target.value = ''
  }

  // Process batch transcription
  const processBatchTranscription = async (file: File) => {
    if (!apiClient) {
      toast.error('API client not initialized')
      return
    }

    setIsUploading(true)
    
    try {
      // Check file format and show appropriate message
      const isMP3 = file.type === 'audio/mpeg' || file.type === 'audio/mp3'
      const isWAV = file.type === 'audio/wav'
      
      let formatInfo = ''
      if (isMP3) {
        formatInfo = ' (will be converted to WAV for processing, stored as MP3)'
      } else if (isWAV) {
        formatInfo = ' (will be converted to WAV for processing, stored as MP3)'
      }
      
      toast.info(`Starting to process audio file: ${file.name}${formatInfo}`)
      
      // Call backend batch transcription API using APIClient pattern
      const token = session?.access_token
      if (!token) {
        toast.error('User not authenticated')
        return
      }
      
      // Prepare form data for API call
      const formData = new FormData()
      formData.append('audio_file', file)
      
      // Debug: log file details before sending
      
      // Use unified API client for file upload
      // Set authentication token
      httpClient.setAuthTokenGetter(() => token)
      
      // API client will auto-detect FormData and set headers correctly
      const result = await httpClient.apiServer('/v1/transcriptions/batch', {
        method: 'POST',
        body: formData
      }) as BatchTranscriptionResponse
      
              // Display detailed success message with statistics
        if (result.status === 'completed' && result.statistics) {
          const stats = result.statistics
          toast.success(
            `🎉 Audio file transcription completed!\n` +
            `📁 File: ${file.name}\n` +
            `🗣️ Speakers: ${stats.speaker_count}\n` +
            `📊 Segments: ${stats.total_segments}\n` +
            `⏱️ Duration: ${Math.round(stats.total_duration_seconds)} seconds\n` +
            `📝 Transcription length: ${stats.transcription_length} characters\n` +
            `💾 Storage format: MP3`,
            { duration: 8000 }
          )
      } else if (result.status === 'placeholder') {
        toast.success('Audio file received, batch transcription feature is under development')
      } else {
        toast.success('Audio file transcription completed')
      }
      
      // Refresh file list and session data
      if (onRefreshSessions) {
        onRefreshSessions()
      }
      
    } catch (error) {
      toast.error(`Failed to process audio file: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setIsUploading(false)
    }
  }

  // Check audio files when sessionId changes
  useEffect(() => {
    if (sessionId) {
      checkSessionAudio(sessionId)
    } else {
      // When sessionId is empty, clear audio state
      setHasAudio(false)
      setAudioUrl(undefined)
    }
  }, [sessionId, checkSessionAudio])

  // Re-check audio files when recording ends
  useEffect(() => {
    if (wasRecordingRef.current && !isRecording && sessionId) {
      // Recording just ended, wait a moment before re-checking audio files
      setTimeout(() => {
        checkSessionAudio(sessionId)
      }, 5000) // Wait 5 seconds to ensure finalize session completion
    }
    
    wasRecordingRef.current = isRecording
  }, [isRecording, sessionId, checkSessionAudio])

  // Expose method to refresh audio files
  const refreshAudioFiles = useCallback(async () => {
    if (sessionId) {
      await checkSessionAudio(sessionId)
    }
  }, [sessionId, checkSessionAudio])
  
  // When parent component requests audio refresh
  useEffect(() => {
    if (onRefreshAudio) {
      onRefreshAudio.current = refreshAudioFiles
    }
  }, [refreshAudioFiles, onRefreshAudio])

  return (
    <div className="h-16 bg-white border-b border-gray-200 px-6 flex items-center flex-shrink-0">
      {/* Audio Player - Full Width */}
      <div className="flex-1 flex items-center space-x-4">
        {hasAudio && !isRecording ? (
          <AudioPlayer 
            audioUrl={audioUrl}
            isVisible={hasAudio && !isRecording}
            className="flex-1"
            onTimeUpdate={onAudioTimeUpdate}
            onSeekTo={onAudioSeekTo}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center">
            {!hasAudio && !isRecording && sessionId && (
              <span className="text-sm text-gray-400">No audio files</span>
            )}
            {isRecording && (
              <span className="text-sm text-red-600">Recording...</span>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex items-center space-x-2 flex-shrink-0">
          {/* AI Summary Button */}
          <Button 
            variant="outline" 
            className="text-blue-600 border-blue-200 hover:bg-blue-50 text-sm px-3 h-8"
            onClick={() => onAISummary?.()}
            disabled={isLoadingSummary || isRecording}
          >
            <MessageSquare className="h-4 w-4 mr-2" />
            {isLoadingSummary ? '生成中...' : 'AI 总结'}
          </Button>

          {/* Audio Import Button */}
          <Button 
            variant="outline" 
            className="text-green-600 border-green-200 hover:bg-green-50 text-sm px-3 h-8"
            onClick={handleAudioImport}
            disabled={isUploading || isRecording}
          >
            <Upload className="h-4 w-4 mr-2" />
            {isUploading ? '处理中...' : '导入音频'}
          </Button>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".wav,.mp3,audio/wav,audio/mpeg,audio/mp3"
        multiple
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />
    </div>
  )
} 