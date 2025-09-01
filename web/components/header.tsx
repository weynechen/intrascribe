'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { MessageSquare, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AudioPlayer } from './audio-player'
import { useAuth } from '@/hooks/useAuth'
import { toast } from 'sonner'

interface HeaderProps {
  isRecording: boolean
  onAISummary?: () => void
  isLoadingSummary?: boolean
  sessionId?: string
  onAudioTimeUpdate?: (currentTime: number) => void
  onAudioSeekTo?: (time: number) => void
  onRefreshSessions?: () => void
  onRefreshAudio?: () => Promise<void>
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
  
  // 使用useAuth获取认证状态
  const { session } = useAuth()
  
  // 使用useRef来跟踪前一个录音状态
  const wasRecordingRef = useRef(isRecording)

  // 检查会话是否有音频文件
  const checkSessionAudio = useCallback(async (sessionId: string) => {
    try {
      // 如果sessionId为空，直接返回
      if (!sessionId) {
        console.log('⚠️ sessionId为空，跳过音频文件检查')
        return
      }
      
      console.log('🔍 检查会话音频文件:', sessionId)

      // 使用useAuth中的session获取token
      const token = session?.access_token

      const response = await fetch(`/api/v1/sessions/${sessionId}/audio_files`, {
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` })
        }
      })
      
      console.log('🌐 Audio files API响应:', {
        status: response.status,
        statusText: response.statusText,
        sessionId: sessionId,
        hasToken: !!token
      })
      
      if (response.ok) {
        const data = await response.json()
        console.log('📊 Audio files数据:', data)
        
        if (data && data.length > 0) {
          const audioFile = data[0] // 取第一个音频文件
          console.log('📁 找到音频文件:', audioFile)
          
          // 将原始URL转换为通过代理访问的URL
          const originalUrl = audioFile.public_url
          let proxyUrl = originalUrl
          
          // 如果是HTTP地址，转换为代理路径
          if (originalUrl && originalUrl.startsWith('http://localhost:54321/')) {
            proxyUrl = originalUrl.replace('http://localhost:54321/', '/')
          } else if (originalUrl && originalUrl.includes('localhost:54321')) {
            // 处理其他可能的格式
            proxyUrl = originalUrl.replace(/https?:\/\/[^/]*localhost:54321\//, '/')
          }
          
          setAudioUrl(proxyUrl)
          setHasAudio(true)
          console.log('✅ 音频URL已设置:', proxyUrl, '(原始URL:', originalUrl, ')')
        } else {
          console.log('📭 该会话暂无音频文件')
          setHasAudio(false)
          setAudioUrl(undefined)
        }
      } else {
        console.error('❌ 获取音频文件API失败:', response.status, response.statusText)
        setHasAudio(false)
        setAudioUrl(undefined)
      }
    } catch (error) {
      console.error('❌ 获取音频文件失败:', error)
      setHasAudio(false)
      setAudioUrl(undefined)
    }
  }, [session?.access_token])

  // Handle audio file import
  const handleAudioImport = () => {
    if (isRecording) {
      toast.warning('录音进行中，无法导入音频文件')
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
    console.log('📁 选择的文件:', selectedFiles.map(f => ({ name: f.name, size: f.size, type: f.type })))

    // Check file formats
    const validFiles = selectedFiles.filter(file => {
      const fileName = file.name.toLowerCase()
      const isWav = fileName.endsWith('.wav') || file.type === 'audio/wav' || file.type === 'audio/x-wav'
      const isMp3 = fileName.endsWith('.mp3') || file.type === 'audio/mpeg' || file.type === 'audio/mp3'
      const isValidFormat = isWav || isMp3
      
      if (!isValidFormat) {
        console.log('❌ 文件格式检查失败:', { name: file.name, type: file.type, fileName })
        toast.error(`文件 ${file.name} 格式不支持，仅支持 WAV 和 MP3 格式`)
      } else {
        console.log('✅ 文件格式检查通过:', { name: file.name, type: file.type })
      }
      return isValidFormat
    })

    if (validFiles.length === 0) {
      toast.error('没有有效的音频文件')
      return
    }

    if (validFiles.length > 1) {
      toast.error('暂时只支持单个文件导入')
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
      toast.error('API客户端未初始化')
      return
    }

    setIsUploading(true)
    
    try {
      // Check file format and show appropriate message
      const isMP3 = file.type === 'audio/mpeg' || file.type === 'audio/mp3'
      const isWAV = file.type === 'audio/wav'
      
      let formatInfo = ''
      if (isMP3) {
        formatInfo = ' (将转换为WAV处理，存储为MP3)'
      } else if (isWAV) {
        formatInfo = ' (将转换为WAV处理，存储为MP3)'
      }
      
      toast.info(`开始处理音频文件: ${file.name}${formatInfo}`)
      
      // Call backend batch transcription API using APIClient pattern
      const token = session?.access_token
      if (!token) {
        toast.error('用户未认证')
        return
      }
      
      // Prepare form data for API call
      const formData = new FormData()
      formData.append('audio_file', file)
      
      // Debug: log file details before sending
      console.log('🔍 发送的文件详情:', {
        name: file.name,
        size: file.size,
        type: file.type,
        lastModified: file.lastModified
      })
      
      // Direct call to backend API with proper authentication
      // Note: Don't set Content-Type header for FormData, browser will set it automatically
      const response = await fetch('/api/v1/transcriptions/batch', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || '批量转录失败')
      }
      
      const result = await response.json()
      console.log('✅ 批量转录完成:', result)
      
              // Display detailed success message with statistics
        if (result.status === 'completed' && result.statistics) {
          const stats = result.statistics
          toast.success(
            `🎉 音频文件转录完成！\n` +
            `📁 文件: ${file.name}\n` +
            `🗣️ 说话人数: ${stats.speaker_count}\n` +
            `📊 转录片段: ${stats.total_segments}个\n` +
            `⏱️ 总时长: ${Math.round(stats.total_duration_seconds)}秒\n` +
            `📝 转录字数: ${stats.transcription_length}字\n` +
            `💾 存储格式: MP3`,
            { duration: 8000 }
          )
      } else if (result.status === 'placeholder') {
        toast.success('音频文件已接收，批量转录功能正在开发中')
      } else {
        toast.success('音频文件转录完成')
      }
      
      // Refresh file list and session data
      if (onRefreshSessions) {
        onRefreshSessions()
      }
      
    } catch (error) {
      console.error('❌ 批量转录失败:', error)
      toast.error(`处理音频文件失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsUploading(false)
    }
  }

  // 当sessionId变化时检查音频文件
  useEffect(() => {
    if (sessionId) {
      checkSessionAudio(sessionId)
    } else {
      // 当sessionId为空时，清理音频状态
      setHasAudio(false)
      setAudioUrl(undefined)
      console.log('🧹 清理音频状态：sessionId为空')
    }
  }, [sessionId, checkSessionAudio])

  // 当录音结束时重新检查音频文件
  useEffect(() => {
    if (wasRecordingRef.current && !isRecording && sessionId) {
      // 录音刚结束，等待一下后重新检查音频文件
      console.log('🔄 录音结束，将在5秒后重新检查音频文件:', sessionId)
      setTimeout(() => {
        console.log('🔍 开始重新检查音频文件:', sessionId)
        checkSessionAudio(sessionId)
      }, 5000) // 等待5秒确保finalize session完成
    }
    
    wasRecordingRef.current = isRecording
  }, [isRecording, sessionId, checkSessionAudio])

  // 暴露刷新音频文件的方法
  const refreshAudioFiles = useCallback(async () => {
    if (sessionId) {
      console.log('🔄 手动刷新音频文件:', sessionId)
      await checkSessionAudio(sessionId)
    }
  }, [sessionId, checkSessionAudio])
  
  // 当父组件请求刷新音频时
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
              <span className="text-sm text-gray-400">暂无音频文件</span>
            )}
            {isRecording && (
              <span className="text-sm text-red-600">录音中...</span>
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