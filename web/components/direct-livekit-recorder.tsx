'use client'

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Mic, MicOff, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import useDirectLiveKit from '@/hooks/useDirectLiveKit'
import { TranscriptEvent } from '@/lib/supabase'
import { toast } from 'sonner'
// 移除本地token生成，使用后端API
import { 
  Room, 
  RoomEvent, 
  Track,
  LocalAudioTrack,
  RemoteAudioTrack
} from 'livekit-client'
import { 
  RoomContext,
  useRoomContext,
  RoomAudioRenderer,
  useTracks,
  StartAudio
} from '@livekit/components-react'

interface DirectLiveKitRecorderProps {
  onTranscript: (transcriptEvent: TranscriptEvent) => void
  onRecordingStateChange: (isRecording: boolean) => void
  onSessionCreated?: (sessionId: string) => void
}

// 内部录音组件实现
function DirectLiveKitRecorderInner({ onTranscript, onRecordingStateChange, onSessionCreated }: DirectLiveKitRecorderProps) {
  const [sessionStarted, setSessionStarted] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const [currentTime, setCurrentTime] = useState('00:00')
  const [roomName, setRoomName] = useState('')

  const { session: authSession } = useAuth()
  const room = useRoomContext()
  
  // 使用直接连接LiveKit的hook
  const { createRoomConfig } = useDirectLiveKit({
    agentName: 'intrascribe-agent-session',
    title: '新录音会话',
    language: 'zh-CN'
  })

  const startTimeRef = useRef<number>()
  const animationFrameRef = useRef<number>()
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)

  // 获取音频轨道进行可视化
  const tracks = useTracks([Track.Source.Microphone], { onlySubscribed: false })

  const showError = useCallback((message: string) => {
    console.error(message)
    toast.error(message)
  }, [])

  const updateAudioLevel = useCallback(() => {
    if (!analyserRef.current) return

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
    analyserRef.current.getByteFrequencyData(dataArray)
    const average = Array.from(dataArray).reduce((a, b) => a + b, 0) / dataArray.length
    setAudioLevel(average / 255)

    animationFrameRef.current = requestAnimationFrame(updateAudioLevel)
  }, [])

  const setupAudioVisualization = useCallback((audioTrack: LocalAudioTrack | RemoteAudioTrack) => {
    try {
      const mediaStreamTrack = audioTrack.mediaStreamTrack
      const stream = new MediaStream([mediaStreamTrack])
      
      audioContextRef.current = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
      analyserRef.current = audioContextRef.current.createAnalyser()
      const audioSource = audioContextRef.current.createMediaStreamSource(stream)
      audioSource.connect(analyserRef.current)
      analyserRef.current.fftSize = 64
      updateAudioLevel()
    } catch (error) {
      console.error('设置音频可视化失败:', error)
    }
  }, [updateAudioLevel])

  const updateTimer = useCallback(() => {
    if (startTimeRef.current) {
      const elapsed = Date.now() - startTimeRef.current
      const minutes = Math.floor(elapsed / 60000)
      const seconds = Math.floor((elapsed % 60000) / 1000)
      setCurrentTime(`${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`)
    }
  }, [])

  // 计时器效果
  useEffect(() => {
    let interval: NodeJS.Timeout
    if (sessionStarted) {
      interval = setInterval(updateTimer, 1000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [sessionStarted, updateTimer])

  // 清理资源
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(e => console.error("Error closing AudioContext:", e))
      }
    }
  }, [])

  // 房间事件监听
  useEffect(() => {
    if (!room) return

    const handleDataReceived = (payload: Uint8Array) => {
      try {
        const textData = new TextDecoder().decode(payload)
        const transcriptData: TranscriptEvent = JSON.parse(textData)
        console.log('📝 收到转录数据:', transcriptData)
        onTranscript(transcriptData)
      } catch (error) {
        console.error('解析转录数据失败:', error)
      }
    }

    const handleConnected = () => {
      console.log('✅ LiveKit房间已连接')
      setIsConnecting(false)
      setSessionStarted(true)
      startTimeRef.current = Date.now()
      onRecordingStateChange(true)
      
      // 使用房间名称作为会话ID
      if (room.name) {
        setRoomName(room.name)
        onSessionCreated?.(room.name)
      }
    }

    const handleDisconnected = () => {
      console.log('🔌 LiveKit房间已断开')
      setSessionStarted(false)
      setIsConnecting(false)
      onRecordingStateChange(false)
      setCurrentTime('00:00')
      startTimeRef.current = undefined
    }

    const handleMediaDevicesError = (error: Error) => {
      showError(`媒体设备错误: ${error.name}: ${error.message}`)
    }

    // 注册事件监听器
    room.on(RoomEvent.DataReceived, handleDataReceived)
    room.on(RoomEvent.Connected, handleConnected)
    room.on(RoomEvent.Disconnected, handleDisconnected)
    room.on(RoomEvent.MediaDevicesError, handleMediaDevicesError)

    return () => {
      room.off(RoomEvent.DataReceived, handleDataReceived)
      room.off(RoomEvent.Connected, handleConnected)
      room.off(RoomEvent.Disconnected, handleDisconnected)
      room.off(RoomEvent.MediaDevicesError, handleMediaDevicesError)
    }
  }, [room, onTranscript, onRecordingStateChange, onSessionCreated, showError])

  // 监听音频轨道变化，设置可视化
  useEffect(() => {
    if (tracks.length > 0) {
      const trackRef = tracks[0]
      const audioTrack = trackRef.publication?.track
      if (audioTrack instanceof LocalAudioTrack || audioTrack instanceof RemoteAudioTrack) {
        setupAudioVisualization(audioTrack)
      }
    }
  }, [tracks, setupAudioVisualization])

  const startRecording = useCallback(async () => {
    if (isConnecting || sessionStarted) {
      console.log('🚫 录音已在进行中，忽略重复请求')
      return
    }

    if (!authSession?.access_token) {
      showError('用户未登录')
      return
    }

    setIsConnecting(true)
    console.log('🎙️ 开始LiveKit录音会话...')

    try {
      // 1. 获取连接配置和token（同时创建会话记录）
      console.log('1️⃣ 获取LiveKit连接配置并创建会话记录...')
      const connectionConfig = await createRoomConfig()

      // 2. 通知父组件会话已创建
      if (connectionConfig.sessionId && onSessionCreated) {
        console.log('📝 通知父组件会话已创建:', connectionConfig.sessionId)
        onSessionCreated(connectionConfig.sessionId)
      }

      // 3. 连接到LiveKit房间
      console.log('2️⃣ 连接LiveKit房间:', connectionConfig.roomName)
      await room.connect(connectionConfig.serverUrl, connectionConfig.token)

      // 4. 连接成功后再启用麦克风
      console.log('3️⃣ 启用麦克风...')
      await room.localParticipant.setMicrophoneEnabled(true)

      console.log('🎉 LiveKit录音流程启动完成')

    } catch (error) {
      console.error('启动LiveKit录音失败:', error)
      showError(`启动录音失败: ${error instanceof Error ? error.message : '未知错误'}`)
      
      setIsConnecting(false)
      setSessionStarted(false)
    }
  }, [isConnecting, sessionStarted, authSession, createRoomConfig, room, showError, onSessionCreated])

  const stopRecording = useCallback(() => {
    if (!sessionStarted) {
      return
    }

    console.log('🛑 停止录音...')
    
    // 清理音频可视化
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(e => console.error("Error closing AudioContext:", e))
      audioContextRef.current = null
    }

    // 断开连接
    room.disconnect()
    
    setSessionStarted(false)
    setIsConnecting(false)
    setIsMuted(false)
    setAudioLevel(0)
  }, [sessionStarted, room])

  const toggleMute = useCallback(async () => {
    try {
      await room.localParticipant.setMicrophoneEnabled(isMuted)
      setIsMuted(!isMuted)
    } catch (error) {
      console.error('切换静音状态失败:', error)
    }
  }, [room, isMuted])

  return (
    <div className="flex flex-col items-center space-y-6">
      {/* 音频可视化 */}
      <div 
        className="w-32 h-32 rounded-full bg-gradient-to-r from-blue-400 to-purple-500 flex items-center justify-center relative overflow-hidden transition-all duration-100"
        style={{
          transform: sessionStarted ? `scale(${1 + audioLevel * 0.3})` : 'scale(1)',
          boxShadow: sessionStarted ? `0 0 ${20 + audioLevel * 40}px rgba(79, 70, 229, 0.6)` : '0 0 0px rgba(79, 70, 229, 0)'
        }}
      >
        <div 
          className="absolute inset-0 bg-white opacity-20 rounded-full transition-transform duration-100"
          style={{ 
            transform: `scale(${1 + audioLevel * 0.5})`,
            filter: `blur(${audioLevel * 2}px)`
          }}
        />
        {sessionStarted && !isMuted ? (
          <Mic className="w-12 h-12 text-white z-10" />
        ) : (
          <MicOff className="w-12 h-12 text-white z-10" />
        )}
      </div>

      {/* 录音时长 */}
      <div className="text-2xl font-mono text-gray-700">
        {currentTime}
      </div>

      {/* 房间信息 */}
      {roomName && (
        <div className="text-sm text-gray-500">
          房间: {roomName}
        </div>
      )}

      {/* 控制按钮 */}
      <div className="flex space-x-4">
        {!sessionStarted ? (
          <Button
            onClick={startRecording}
            disabled={isConnecting}
            className="px-8 py-3 bg-red-500 hover:bg-red-600 text-white rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isConnecting ? '连接中...' : '开始录音'}
          </Button>
        ) : (
          <>
            <Button
              onClick={toggleMute}
              variant="outline"
              className="px-4 py-2 rounded-full"
              disabled={!sessionStarted || isConnecting}
            >
              {isMuted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </Button>
            <Button
              onClick={stopRecording}
              className="px-6 py-3 bg-gray-500 hover:bg-gray-600 text-white rounded-full"
            >
              <Square className="w-5 h-5 mr-2" />
              停止录音
            </Button>
          </>
        )}
      </div>

      {/* 连接状态显示 */}
      {isConnecting && (
        <div className="text-sm text-gray-500 animate-pulse">
          正在连接LiveKit服务器...
        </div>
      )}
    </div>
  )
}

// 主要的录音组件，包含RoomContext
export function DirectLiveKitRecorder({ onTranscript, onRecordingStateChange, onSessionCreated }: DirectLiveKitRecorderProps) {
  const room = useMemo(() => new Room({
    // 自适应流质量优化
    adaptiveStream: true,
    // 启用动态质量优化
    dynacast: true,
  }), [])

  // 清理房间资源
  useEffect(() => {
    return () => {
      room.disconnect()
    }
  }, [room])

  return (
    <RoomContext.Provider value={room}>
      <div data-lk-theme="default">
        <DirectLiveKitRecorderInner 
          onTranscript={onTranscript}
          onRecordingStateChange={onRecordingStateChange}
          onSessionCreated={onSessionCreated}
        />
        {/* LiveKit音频渲染器 */}
        <RoomAudioRenderer />
        {/* 自动启动音频 */}
        <StartAudio label="启动音频" />
      </div>
    </RoomContext.Provider>
  )
}
