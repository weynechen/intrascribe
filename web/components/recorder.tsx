'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Mic, MicOff, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useRecordingSessions } from '@/hooks/useRecordingSessions'
import { TranscriptEvent } from '@/lib/supabase'
import { toast } from 'sonner'

interface RecorderProps {
  onTranscript: (transcriptEvent: TranscriptEvent) => void
  onRecordingStateChange: (isRecording: boolean) => void
  onSessionCreated?: (sessionId: string) => void
}

export function Recorder({ onTranscript, onRecordingStateChange, onSessionCreated }: RecorderProps) {
  const [isRecording, setIsRecording] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const [currentTime, setCurrentTime] = useState('00:00')
  const [isStopping, setIsStopping] = useState(false)

  const { session: authSession } = useAuth()
  const { createSession, finalizeSession } = useRecordingSessions()

  const peerConnectionRef = useRef<RTCPeerConnection | null>(null)
  const sessionIdRef = useRef<string>('')
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animationFrameRef = useRef<number>()
  const eventSourceRef = useRef<EventSource | null>(null)
  const startTimeRef = useRef<number>()
  const transcriptBufferRef = useRef<string>('')

  const showError = useCallback((message: string) => {
    try {
      console.error(message)
      toast.error(message)
    } catch {
      // Fallback in case console.error fails
      try {
        console.log('Error:', message)
      } catch {
        // If even console.log fails, ignore
      }
    }
  }, [])

  const updateAudioLevel = useCallback(() => {
    if (!analyserRef.current) return

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
    analyserRef.current.getByteFrequencyData(dataArray)
    const average = Array.from(dataArray).reduce((a, b) => a + b, 0) / dataArray.length
    setAudioLevel(average / 255)

    animationFrameRef.current = requestAnimationFrame(updateAudioLevel)
  }, [])

  const setupAudioVisualization = useCallback((stream: MediaStream) => {
    audioContextRef.current = new (window.AudioContext || (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext || AudioContext)()
    analyserRef.current = audioContextRef.current.createAnalyser()
    const audioSource = audioContextRef.current.createMediaStreamSource(stream)
    audioSource.connect(analyserRef.current)
    analyserRef.current.fftSize = 64
    updateAudioLevel()
  }, [updateAudioLevel])

  const updateTimer = useCallback(() => {
    if (startTimeRef.current) {
      const elapsed = Date.now() - startTimeRef.current
      const minutes = Math.floor(elapsed / 60000)
      const seconds = Math.floor((elapsed % 60000) / 1000)
      setCurrentTime(`${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`)
    }
  }, [])

  useEffect(() => {
    let interval: NodeJS.Timeout
    if (isRecording) {
      interval = setInterval(updateTimer, 1000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isRecording, updateTimer])

  // Component unmount cleanup effect
  useEffect(() => {
    return () => {
      // Clean up all resources when component unmounts
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(e => console.error("Error closing AudioContext on unmount:", e))
        audioContextRef.current = null
      }
      if (peerConnectionRef.current) {
        peerConnectionRef.current.getSenders().forEach(sender => {
          if (sender.track) {
            sender.track.stop()
          }
        })
        peerConnectionRef.current.close()
        peerConnectionRef.current = null
      }
    }
  }, [])

  // 设置实时转录监听
  const setupTranscriptListener = useCallback((sessionId: string, token: string) => {
    // 在开发环境下直接连接到后端，生产环境使用代理
    const transcriptUrl = process.env.NODE_ENV === 'development' 
      ? `http://localhost:8000/transcript?webrtc_id=${sessionId}&token=${token}`
      : `/transcript?webrtc_id=${sessionId}&token=${token}`
    console.log('🎧 开始监听实时转录:', transcriptUrl)
    
    eventSourceRef.current = new EventSource(transcriptUrl)
    
    eventSourceRef.current.addEventListener('output', (event) => {
      try {
        const transcriptData: TranscriptEvent = JSON.parse(event.data)
        console.log('📝 收到转录数据:', transcriptData)
        
        // 更新转录缓冲区
        if (transcriptData.is_final) {
          transcriptBufferRef.current += transcriptData.text + ' '
        }
        
        // 通知上级组件 - 传递完整的转录事件对象
        try {
          onTranscript(transcriptData)
        } catch (callbackError) {
          console.error('onTranscript callback error:', callbackError)
        }
      } catch (error) {
        console.error('解析转录数据失败:', error)
      }
    })
    
    eventSourceRef.current.addEventListener('error', (error) => {
      console.error('转录监听错误:', error)
      showError('转录连接中断')
    })
    
    eventSourceRef.current.addEventListener('open', () => {
      console.log('✅ 转录连接已建立')
    })
  }, [onTranscript, showError])

  const stopRecording = useCallback(async () => {
    // 防止重复调用
    if (isStopping) {
      console.log('🚫 正在停止录音中，忽略重复请求')
      return
    }

    console.log('🛑 停止录音...')
    
    // 立即设置停止状态，防止重复点击
    setIsStopping(true)
    
    // 立即停止UI状态更新（计时器、录音状态等）
    setIsRecording(false)
    setIsConnecting(false)
    setIsMuted(false)
    setAudioLevel(0)
    setCurrentTime('00:00')
    
    // 立即通知上级组件状态变化
    try {
      onRecordingStateChange(false)
    } catch (callbackError) {
      console.error('onRecordingStateChange callback error:', callbackError)
    }
    
    // 然后在后台进行清理工作
    try {
      // 停止音频可视化
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      
      // 关闭转录监听连接
      if (eventSourceRef.current) {
        console.log('🔌 关闭转录监听连接...')
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      
      // 关闭音频上下文
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(e => console.error("Error closing AudioContext:", e))
        audioContextRef.current = null
      }
      
      // 关闭WebRTC连接
      if (peerConnectionRef.current) {
        peerConnectionRef.current.getSenders().forEach(sender => {
          if (sender.track) {
            sender.track.stop()
          }
        })
        peerConnectionRef.current.close()
        peerConnectionRef.current = null
      }

      // 完成会话（在后台进行）
      if (sessionIdRef.current) {
        console.log('🏁 完成会话:', sessionIdRef.current)
        try {
          await finalizeSession(sessionIdRef.current)
          console.log('✅ 会话完成成功')
        } catch (error) {
          console.error('完成会话失败:', error)
          // 即使finalize失败，也不影响UI状态
        }
      }
      
      // 清理引用
      startTimeRef.current = undefined
      sessionIdRef.current = ''
      transcriptBufferRef.current = ''
      
    } catch (error) {
      console.error('停止录音时发生错误:', error)
    } finally {
      // 重置停止状态
      setIsStopping(false)
      console.log('🏁 录音停止完成')
    }
  }, [isStopping, onRecordingStateChange, finalizeSession])

  const startRecording = useCallback(async () => {
    // Prevent multiple concurrent recording attempts
    if (isConnecting || isRecording || isStopping) {
      console.log('🚫 录音已在进行中或正在停止，忽略重复请求')
      return
    }

    if (!authSession?.access_token) {
      showError('用户未登录')
      return
    }

    // Clean up any existing connections before starting new one
    if (peerConnectionRef.current) {
      console.log('🧹 清理现有连接...')
      await stopRecording()
      // Wait a bit for cleanup to complete
      await new Promise(resolve => setTimeout(resolve, 500))
    }

    // 重置所有状态
    setIsStopping(false)
    setIsConnecting(true)
    console.log('🎙️ 开始录音流程...')
    
    try {
      // Step 0: 检查录音设备是否存在
      console.log('0️⃣ 检查录音设备...')
      if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        try {
          const devices = await navigator.mediaDevices.enumerateDevices()
          const audioInputDevices = devices.filter(device => device.kind === 'audioinput')
          if (audioInputDevices.length === 0) {
            throw new Error('未检测到录音设备，请连接麦克风后重试')
          }
          console.log('✅ 检测到录音设备:', audioInputDevices.length, '个')
        } catch (enumError) {
          console.error('设备检查失败:', enumError)
          throw new Error('无法检测录音设备，请确认麦克风已连接')
        }
      } else {
        throw new Error('浏览器不支持录音功能')
      }

      // Step 1: 创建业务会话
      console.log('1️⃣ 创建业务会话...')
      const sessionResult = await createSession('新的录音会话')
      
      if (!sessionResult) {
        throw new Error('创建会话失败')
      }
      
      sessionIdRef.current = sessionResult.session_id
      console.log('✅ 会话创建成功:', sessionIdRef.current)
      
      // 通知上级组件会话已创建
      try {
        onSessionCreated?.(sessionResult.session_id)
      } catch (callbackError) {
        console.error('onSessionCreated callback error:', callbackError)
        // Continue execution even if callback fails
      }

      // Step 2: 获取音频流并建立WebRTC连接
      console.log('2️⃣ 获取音频流...')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      setupAudioVisualization(stream)

      // 使用空配置，让浏览器使用默认STUN服务器
      const config = undefined
      peerConnectionRef.current = new RTCPeerConnection(config)

      stream.getTracks().forEach(track => {
        peerConnectionRef.current!.addTrack(track, stream)
      })

      peerConnectionRef.current.addEventListener('connectionstatechange', () => {
        console.log('WebRTC连接状态:', peerConnectionRef.current?.connectionState)
        if (peerConnectionRef.current?.connectionState === 'connected') {
          setIsConnecting(false)
          setIsRecording(true)
          startTimeRef.current = Date.now()
          try {
            onRecordingStateChange(true)
          } catch (callbackError) {
            console.error('onRecordingStateChange callback error:', callbackError)
          }
          console.log('✅ WebRTC连接已建立')
        }
      })

      // ICE候选处理
      peerConnectionRef.current.onicecandidate = ({ candidate }) => {
        if (candidate) {
          // console.debug("发送ICE候选:", candidate)
          fetch('/webrtc/offer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              candidate: candidate.toJSON(),
              webrtc_id: sessionIdRef.current, // 使用session_id作为webrtc_id
              type: "ice-candidate",
            })
          }).catch(e => console.error("发送ICE候选失败:", e))
        }
      }

      // 创建数据通道
      const dataChannel = peerConnectionRef.current.createDataChannel('text')
      dataChannel.onmessage = async (event) => {
        console.log('收到数据通道消息:', event.data)
        
        try {
          const eventJson = JSON.parse(event.data)
          if (eventJson.type === "error") {
            showError(eventJson.message)
          } else if (eventJson.type === "send_input") {
            // 发送输入信号到后端
            const response = await fetch('/send_input', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                webrtc_id: sessionIdRef.current,
                transcript: ""
              })
            })
            if (!response.ok) {
              console.error('发送输入信号失败')
            }
          }
        } catch (e) {
          console.error('解析数据通道消息失败:', e)
        }
      }

      // Step 3: 建立WebRTC连接
      console.log('3️⃣ 建立WebRTC连接...')
      const offer = await peerConnectionRef.current.createOffer()
      await peerConnectionRef.current.setLocalDescription(offer)

      // 使用session_id作为webrtc_id发送offer
      const response = await fetch('/webrtc/offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sdp: peerConnectionRef.current.localDescription!.sdp,
          type: peerConnectionRef.current.localDescription!.type,
          webrtc_id: sessionIdRef.current // 关键：使用session_id
        })
      })

      if (!response.ok) {
        throw new Error(`WebRTC连接失败: ${response.status}`)
      }

      const serverResponse = await response.json()

      if (serverResponse.status === 'failed') {
        showError(serverResponse.meta?.error === 'concurrency_limit_reached'
          ? `连接数过多，最大限制为 ${serverResponse.meta?.limit}`
          : (serverResponse.meta?.error || '连接失败'))
        await stopRecording()
        return
      }

      // 设置远程描述
      if (serverResponse.sdp) {
        await peerConnectionRef.current.setRemoteDescription({
          type: 'answer',
          sdp: serverResponse.sdp
        })
        console.log('✅ WebRTC Answer已设置')
      }

      // Step 4: 设置实时转录监听
      console.log('4️⃣ 设置实时转录监听...')
      setupTranscriptListener(sessionIdRef.current, authSession.access_token)

      console.log('🎉 录音流程启动完成')
      
    } catch (error) {
      console.error('启动录音失败:', error)
      showError(`启动录音失败: ${error instanceof Error ? error.message : '未知错误'}`)
      
      // Reset state on error - but don't call stopRecording if recording never started
      setIsConnecting(false)
      setIsRecording(false)
      setIsStopping(false)
      
      // Only call stopRecording if we actually started recording (have active connections)
      if (peerConnectionRef.current || eventSourceRef.current || audioContextRef.current) {
        await stopRecording()
      }
    }
  }, [isConnecting, isRecording, isStopping, authSession, createSession, setupTranscriptListener, setupAudioVisualization, showError, stopRecording, onRecordingStateChange, onSessionCreated])

  const toggleMute = useCallback(() => {
    if (peerConnectionRef.current) {
      const audioTracks = peerConnectionRef.current.getSenders()
        .map(sender => sender.track)
        .filter(track => track && track.kind === 'audio') as MediaStreamTrack[]
      
      audioTracks.forEach(track => {
        track.enabled = isMuted
      })
    }
    setIsMuted(!isMuted)
  }, [isMuted])

  return (
    <div className="flex flex-col items-center space-y-4">
      {/* 音频可视化 */}
      <div className="w-32 h-32 rounded-full bg-gradient-to-r from-blue-400 to-purple-500 flex items-center justify-center relative overflow-hidden">
        <div 
          className="absolute inset-0 bg-white opacity-30 rounded-full transition-transform duration-100"
          style={{ 
            transform: `scale(${1 + audioLevel * 0.5})`,
            filter: `blur(${audioLevel * 2}px)`
          }}
        />
        {isRecording ? (
          <Mic className="w-12 h-12 text-white z-10" />
        ) : (
          <MicOff className="w-12 h-12 text-white z-10" />
        )}
      </div>

      {/* 录音时长 */}
      <div className="text-2xl font-mono text-gray-700">
        {currentTime}
      </div>

      {/* 控制按钮 */}
      <div className="flex space-x-4">
        {!isRecording && !isStopping ? (
          <Button
            onClick={startRecording}
            disabled={isConnecting || isRecording || isStopping}
            className="px-6 py-3 bg-red-500 hover:bg-red-600 text-white rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isConnecting ? '连接中...' : '开始录音'}
          </Button>
        ) : (
          <>
            <Button
              onClick={toggleMute}
              variant="outline"
              className="px-4 py-2 rounded-full"
              disabled={!isRecording || isStopping}
            >
              {isMuted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </Button>
            <Button
              onClick={stopRecording}
              className="px-6 py-3 bg-gray-500 hover:bg-gray-600 text-white rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isStopping}
            >
              <Square className="w-5 h-5 mr-2" />
              {isStopping ? '正在停止...' : '停止录音'}
            </Button>
          </>
        )}
      </div>

      {/* 状态指示 */}
      {isConnecting && (
        <div className="text-sm text-gray-500">
          正在建立连接...
        </div>
      )}
      {isRecording && !isStopping && (
        <div className="text-sm text-green-600">
          🔴 录音中...
        </div>
      )}
      {isStopping && (
        <div className="text-sm text-blue-600">
          🔄 正在停止录音，处理数据中...
        </div>
      )}
    </div>
  )
} 