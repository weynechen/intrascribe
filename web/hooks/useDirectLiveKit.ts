'use client'

import { useCallback, useState } from 'react'
import { useAuth } from './useAuth'
import { apiPost, httpClient } from '@/lib/api-client'

// Direct LiveKit connection configuration
export interface LiveKitDirectConfig {
  serverUrl: string
  roomName: string
  participantName: string
  sessionId?: string  // Optional session ID field
}

interface AppConfig {
  agentName?: string
  title?: string
  language?: string
}

interface LiveKitConnectionDetails {
  serverUrl: string
  roomName: string
  participantName: string
  participantToken: string
  sessionId: string
}

export default function useDirectLiveKit(appConfig: AppConfig = {}) {
  const { session: authSession, user } = useAuth()
  const [loading, setLoading] = useState(false)

  const generateRoomConfig = useCallback((): LiveKitDirectConfig => {
    // Generate random room name
    const timestamp = Date.now()
    const randomSuffix = Math.random().toString(36).substring(2, 8)
    const roomName = `intrascribe_room_${timestamp}_${randomSuffix}`
    
    // Use user info as participant name
    const participantName = user?.email || `user_${randomSuffix}`
    
    // Get LiveKit server URL from environment variables or config
    const serverUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL || 'ws://localhost:7880'
    

    return {
      serverUrl,
      roomName,
      participantName
    }
  }, [user?.email, appConfig.agentName])

  const createRoomConfig = useCallback(async (): Promise<LiveKitDirectConfig & { token: string; sessionId: string }> => {
    if (!authSession?.access_token) {
      throw new Error('User not logged in')
    }

    setLoading(true)
    
    try {
      
      // Use unified API client to get connection details
      httpClient.setAuthTokenGetter(() => authSession.access_token)
      const connectionDetails = await apiPost('api', '/v1/livekit/connection-details', {
        room_config: appConfig.agentName ? {
          agents: [{ agent_name: appConfig.agentName }]
        } : undefined,
        title: appConfig.title || 'New recording session',
        language: appConfig.language || 'zh-CN'
      }) as LiveKitConnectionDetails
      
      
      return {
        serverUrl: connectionDetails.serverUrl,
        roomName: connectionDetails.roomName,
        participantName: connectionDetails.participantName,
        token: connectionDetails.participantToken,
        sessionId: connectionDetails.sessionId
      }
      
    } catch (error) {
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
