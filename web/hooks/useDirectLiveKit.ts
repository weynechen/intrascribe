'use client'

import { useCallback, useState } from 'react'
import { useAuth } from './useAuth'
import { apiPost, httpClient } from '@/lib/api-client'

// 直接连接LiveKit的配置
export interface LiveKitDirectConfig {
  serverUrl: string
  roomName: string
  participantName: string
  sessionId?: string  // 可选的会话ID字段
}

interface AppConfig {
  agentName?: string
  title?: string
  language?: string
}

export default function useDirectLiveKit(appConfig: AppConfig = {}) {
  const { session: authSession, user } = useAuth()
  const [loading, setLoading] = useState(false)

  const generateRoomConfig = useCallback((): LiveKitDirectConfig => {
    // 生成随机房间名
    const timestamp = Date.now()
    const randomSuffix = Math.random().toString(36).substring(2, 8)
    const roomName = `intrascribe_room_${timestamp}_${randomSuffix}`
    
    // 使用用户信息作为参与者名称
    const participantName = user?.email || `user_${randomSuffix}`
    
    // 从环境变量或配置获取LiveKit服务器URL
    const serverUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL || 'ws://localhost:7880'
    
    console.log('🏠 生成房间配置:', {
      roomName,
      participantName,
      serverUrl,
      agentName: appConfig.agentName
    })

    return {
      serverUrl,
      roomName,
      participantName
    }
  }, [user?.email, appConfig.agentName])

  const createRoomConfig = useCallback(async (): Promise<LiveKitDirectConfig & { token: string; sessionId: string }> => {
    if (!authSession?.access_token) {
      throw new Error('用户未登录')
    }

    setLoading(true)
    
    try {
      console.log('🔧 创建LiveKit房间配置...', appConfig)
      
      // 使用统一API客户端获取连接详情
      httpClient.setAuthTokenGetter(() => authSession.access_token)
      const connectionDetails = await apiPost('api', '/v1/livekit/connection-details', {
        room_config: appConfig.agentName ? {
          agents: [{ agent_name: appConfig.agentName }]
        } : undefined,
        title: appConfig.title || '新录音会话',
        language: appConfig.language || 'zh-CN'
      })
      
      console.log('✅ LiveKit连接详情获取成功:', connectionDetails)
      
      return {
        serverUrl: connectionDetails.serverUrl,
        roomName: connectionDetails.roomName,
        participantName: connectionDetails.participantName,
        token: connectionDetails.participantToken,
        sessionId: connectionDetails.sessionId
      }
      
    } catch (error) {
      console.error('创建房间配置失败:', error)
      throw error
    } finally {
      setLoading(false)
    }
  }, [authSession?.access_token, appConfig])

  return {
    loading,
    createRoomConfig,
    generateRoomConfig
  }
}
