'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { supabase, RecordingSessionWithRelations, APIClient, subscriptionManager } from '@/lib/supabase'
import { useAuth } from './useAuth'
import { toast } from 'sonner'
import { isSyncResponse, isAsyncResponse } from '@/lib/api-types'

export function useRecordingSessions() {
  const { user, session } = useAuth()
  const [sessions, setSessions] = useState<RecordingSessionWithRelations[]>([])
  const [loading, setLoading] = useState(true)
  const [apiClient, setApiClient] = useState<APIClient | null>(null)
  const channelNameRef = useRef<string>('')
  const transcriptionChannelNameRef = useRef<string>('')
  const fetchingRef = useRef(false)
  const lastUserIdRef = useRef<string>('')
  const initializedRef = useRef(false)

  // 初始化API客户端
  useEffect(() => {
    if (session?.access_token) {
      const client = new APIClient('/api/v1', () => session.access_token)
      setApiClient(client)
    }
  }, [session?.access_token])

  // 获取用户的录音会话 - 使用稳定的函数
  const fetchSessions = useCallback(async (userId: string, force: boolean = false) => {
    if (!userId || (fetchingRef.current && !force)) return

    fetchingRef.current = true
    setLoading(true)
    
    try {
      const { data, error } = await supabase
        .from('recording_sessions')
        .select(`
          *,
          audio_files (
            id,
            original_filename,
            duration_seconds,
            upload_status,
            file_size_bytes,
            format
          ),
          transcriptions (
            id,
            content,
            segments,
            confidence_score,
            word_count,
            status,
            created_at
          ),
          ai_summaries (
            id,
            summary,
            key_points,
            quality_rating,
            status,
            created_at
          )
        `)
        .eq('user_id', userId)
        .order('created_at', { ascending: false })

      if (error) throw error
      
      console.log('📊 获取到录音会话数据:', data?.length || 0, '条记录')
      
      // 手动验证和转换数据类型
      const validatedSessions: RecordingSessionWithRelations[] = (data || []).map((item: any) => ({
        // 基础会话字段
        id: String(item.id),
        user_id: String(item.user_id),
        title: String(item.title),
        description: item.description ? String(item.description) : undefined,
        status: item.status || 'created',
        language: String(item.language || 'zh-CN'),
        stt_model: item.stt_model ? String(item.stt_model) : undefined,
        started_at: item.started_at ? String(item.started_at) : undefined,
        ended_at: item.ended_at ? String(item.ended_at) : undefined,
        duration_seconds: item.duration_seconds ? Number(item.duration_seconds) : undefined,
        metadata: item.metadata || {},
        tags: Array.isArray(item.tags) ? item.tags : [],
        created_at: String(item.created_at),
        updated_at: String(item.updated_at),
        
        // 关联数据 - 处理可能的查询错误
        audio_files: Array.isArray(item.audio_files) ? item.audio_files : [],
        transcriptions: Array.isArray(item.transcriptions) ? item.transcriptions : [],
        ai_summaries: Array.isArray(item.ai_summaries) ? item.ai_summaries : []
      }))
      
      setSessions(validatedSessions)
    } catch (error) {
      console.error('获取录音会话失败:', error)
      toast.error('获取录音会话失败')
    } finally {
      setLoading(false)
      fetchingRef.current = false
    }
  }, [])

  // 处理转录实时更新 - 使用useRef保持稳定引用
  const handleTranscriptionChangeRef = useRef((payload: any) => {
    console.log('📡 转录数据实时变化:', {
      eventType: payload.eventType,
      table: payload.table,
      sessionId: payload.new?.session_id || payload.old?.session_id,
      transcriptionId: payload.new?.id || payload.old?.id,
      timestamp: new Date().toISOString()
    })
    
    // 转录数据更新时，刷新相关会话数据
    if (payload.eventType === 'UPDATE' && payload.new?.session_id) {
      console.log('🔄 转录数据更新，刷新会话数据以获取最新转录内容')
      
      // 延迟刷新，确保数据库操作完成
      setTimeout(() => {
        if (lastUserIdRef.current) {
          fetchSessions(lastUserIdRef.current)
        }
      }, 500)
    }
  })

  // 处理实时订阅数据变化 - 使用useRef保持稳定引用
  const handleRealtimeChangeRef = useRef((payload: any) => {
    console.log('📡 录音会话实时变化:', {
      eventType: payload.eventType,
      table: payload.table,
      schema: payload.schema,
      newId: payload.new?.id,
      oldId: payload.old?.id,
      newStatus: payload.new?.status,
      fullPayload: payload
    })
    
    switch (payload.eventType) {
      case 'INSERT':
        if (payload.new) {
          setSessions(prev => {
            // 检查是否已存在，避免重复添加
            if (prev.some(s => s.id === payload.new.id)) {
              console.log('⚠️ 会话已存在，跳过INSERT:', payload.new.id)
              return prev
            }
            console.log('✅ 通过实时订阅添加新会话:', payload.new.id, payload.new.title)
            console.log('🔄 添加前会话数量:', prev.length, '添加后预期数量:', prev.length + 1)
            
            // 先添加会话到列表中，但不设置关联数据
            const newSession: RecordingSessionWithRelations = {
              ...payload.new,
              // 保留原始关联数据，如果有的话
              audio_files: payload.new.audio_files || [],
              transcriptions: payload.new.transcriptions || [],
              ai_summaries: payload.new.ai_summaries || []
            }
            const newSessions = [newSession, ...prev]
            console.log('✅ 新会话列表构建完成，总数:', newSessions.length, '第一个会话ID:', newSessions[0]?.id)
            
            return newSessions
          })
          
          // INSERT事件通常不包含关联数据，需要刷新获取完整数据
          console.log('🔄 INSERT事件不包含完整关联数据，1秒后刷新会话数据')
          setTimeout(() => {
            if (lastUserIdRef.current) {
              fetchSessions(lastUserIdRef.current)
            }
          }, 1000)
        }
        break
      case 'UPDATE':
        if (payload.new) {
          console.log('✅ 通过实时订阅更新会话:', payload.new.id, '状态:', payload.new.status)
          setSessions(prev => {
            const beforeUpdateCount = prev.length
            const updated = prev.map(session =>
              session.id === payload.new.id 
                ? { ...session, ...payload.new } 
                : session
            )
            console.log('🔄 更新后会话数量检查 - 更新前:', beforeUpdateCount, '更新后:', updated.length)
            if (beforeUpdateCount !== updated.length) {
              console.warn('⚠️ 更新操作意外改变了会话数量！')
            }
            return updated
          })
          
          // 如果状态变为 completed，说明可能有新的转录数据，需要刷新完整数据
          if (payload.new.status === 'completed') {
            console.log('🔄 会话状态变为completed，刷新会话数据以获取最新转录内容')
            // 立即刷新数据，确保前端能及时获取重新处理后的结果
            if (lastUserIdRef.current) {
              fetchSessions(lastUserIdRef.current)
            }
          }
          
          // 特别处理：如果状态从processing变为completed，说明重新处理完成
          if (payload.old?.status === 'processing' && payload.new.status === 'completed') {
            console.log('🎉 检测到重新处理完成，多次刷新确保数据同步')
            
            // 立即刷新第一次
            if (lastUserIdRef.current) {
              fetchSessions(lastUserIdRef.current)
            }
            
            // 1秒后再刷新一次，确保转录数据完全同步
            setTimeout(() => {
              if (lastUserIdRef.current) {
                console.log('🔄 重新转录完成后的延迟刷新')
                fetchSessions(lastUserIdRef.current)
              }
            }, 1500)
            
            // 3秒后最后一次刷新，确保所有数据都已同步
            setTimeout(() => {
              if (lastUserIdRef.current) {
                console.log('🔄 重新转录完成后的最终刷新')
                fetchSessions(lastUserIdRef.current)
              }
            }, 3000)
          }
        }
        break
      case 'DELETE':
        if (payload.old) {
          console.log('✅ 通过实时订阅删除会话:', payload.old.id)
          setSessions(prev => {
            const beforeDeleteCount = prev.length
            const filtered = prev.filter(session => session.id !== payload.old.id)
            console.log('🔄 删除后会话数量检查 - 删除前:', beforeDeleteCount, '删除后:', filtered.length)
            return filtered
          })
        }
        break
      default:
        console.log('🔍 未知的实时订阅事件类型:', payload.eventType)
    }
  })

  // 主要的useEffect - 用于初始化和用户变化
  useEffect(() => {
    // 如果没有用户，清空数据
    if (!user?.id) {
      setSessions([])
      setLoading(false)
      lastUserIdRef.current = ''
      initializedRef.current = false
      
      // 清理订阅
      if (channelNameRef.current) {
        try {
          console.log('🧹 用户登出，清理订阅:', channelNameRef.current)
          subscriptionManager.removeChannel(channelNameRef.current)
        } catch (error) {
          console.error('清理订阅失败:', error)
        }
        channelNameRef.current = ''
      }
      return
    }

    // 如果用户没有变化且已初始化，不重复处理
    if (lastUserIdRef.current === user.id && initializedRef.current) {
      console.log('⚠️ 用户未变化且已初始化，跳过重复处理')
      return
    }

    // 防止重复初始化
    if (initializedRef.current && lastUserIdRef.current === user.id) {
      console.log('⚠️ 已初始化相同用户，跳过')
      return
    }

    console.log('🔄 用户变化，初始化会话订阅:', {
      oldUserId: lastUserIdRef.current,
      newUserId: user.id,
      wasInitialized: initializedRef.current
    })

    lastUserIdRef.current = user.id
    initializedRef.current = true

    // 清理之前的订阅
    if (channelNameRef.current) {
      try {
        console.log('🧹 清理之前的订阅:', channelNameRef.current)
        subscriptionManager.removeChannel(channelNameRef.current)
      } catch (error) {
        console.error('清理之前的订阅失败:', error)
      }
      channelNameRef.current = ''
    }

    // 内联获取数据函数，避免依赖外部函数
    const loadSessions = async (userId: string) => {
      if (!userId || fetchingRef.current) return

      fetchingRef.current = true
      setLoading(true)
      
      try {
        const { data, error } = await supabase
          .from('recording_sessions')
          .select(`
            *,
            audio_files (
              id,
              original_filename,
              duration_seconds,
              upload_status,
              file_size_bytes,
              format
            ),
            transcriptions (
              id,
              content,
              segments,
              confidence_score,
              word_count,
              status,
              created_at
            ),
            ai_summaries (
              id,
              summary,
              key_points,
              quality_rating,
              status,
              created_at
            )
          `)
          .eq('user_id', userId)
          .order('created_at', { ascending: false })

        if (error) throw error
        
        console.log('📊 获取到录音会话数据:', data?.length || 0, '条记录')
        
        // 手动验证和转换数据类型（loadSessions版本）
        const validatedSessions: RecordingSessionWithRelations[] = (data || []).map((item: any) => ({
          // 基础会话字段
          id: String(item.id),
          user_id: String(item.user_id),
          title: String(item.title),
          description: item.description ? String(item.description) : undefined,
          status: item.status || 'created',
          language: String(item.language || 'zh-CN'),
          stt_model: item.stt_model ? String(item.stt_model) : undefined,
          started_at: item.started_at ? String(item.started_at) : undefined,
          ended_at: item.ended_at ? String(item.ended_at) : undefined,
          duration_seconds: item.duration_seconds ? Number(item.duration_seconds) : undefined,
          metadata: item.metadata || {},
          tags: Array.isArray(item.tags) ? item.tags : [],
          created_at: String(item.created_at),
          updated_at: String(item.updated_at),
          
          // 关联数据 - 处理可能的查询错误
          audio_files: Array.isArray(item.audio_files) ? item.audio_files : [],
          transcriptions: Array.isArray(item.transcriptions) ? item.transcriptions : [],
          ai_summaries: Array.isArray(item.ai_summaries) ? item.ai_summaries : []
        }))
        
        setSessions(validatedSessions)
      } catch (error) {
        console.error('获取录音会话失败:', error)
        toast.error('获取录音会话失败')
      } finally {
        setLoading(false)
        fetchingRef.current = false
      }
    }

    // 获取数据
    loadSessions(user.id)

    // 延迟创建订阅，避免与数据获取冲突
    const createSubscription = () => {
      // 再次检查是否已有订阅
      if (channelNameRef.current) {
        console.log('⚠️ 订阅已存在，跳过创建:', channelNameRef.current)
        return
      }

      // 检查是否还是同一个用户（防止用户快速切换导致的问题）
      if (lastUserIdRef.current !== user.id) {
        console.log('⚠️ 用户已变化，取消订阅创建')
        return
      }

      try {
        const channelName = `user-sessions-${user.id}-${Date.now()}`
        console.log('📡 创建新订阅:', channelName)
        console.log('🔧 订阅参数:', {
          userId: user.id,
          handlerFunction: 'handleRealtimeChangeRef.current',
          activeChannelsCount: subscriptionManager.getActiveChannelCount(),
          existingChannels: subscriptionManager.getActiveChannels()
        })
        
        const channel = subscriptionManager.createChannel(channelName, user.id, handleRealtimeChangeRef.current)
        if (channel) {
          channelNameRef.current = channelName
          console.log('✅ 会话订阅创建成功，频道名:', channelName)
        } else {
          console.error('❌ 会话订阅创建失败')
        }

        // 注意：转录订阅将在单独的useEffect中处理，以避免依赖cycles
      } catch (error) {
        console.error('创建实时订阅失败:', error)
      }
    }

    // 延迟创建订阅，确保数据加载完成
    const subscriptionTimer = setTimeout(createSubscription, 1200) // 增加延迟以确保sessions数据已加载

    return () => {
      console.log('🧹 useEffect清理函数执行')
      clearTimeout(subscriptionTimer)
      
      // 清理订阅
      if (channelNameRef.current) {
        try {
          console.log('🗑️ 清理会话订阅:', channelNameRef.current)
          subscriptionManager.removeChannel(channelNameRef.current)
        } catch (error) {
          console.error('cleanup会话订阅失败:', error)
        }
        channelNameRef.current = ''
      }
      
      // 清理转录订阅
      if (transcriptionChannelNameRef.current) {
        try {
          console.log('🗑️ 清理转录订阅:', transcriptionChannelNameRef.current)
          subscriptionManager.removeChannel(transcriptionChannelNameRef.current)
        } catch (error) {
          console.error('cleanup转录订阅失败:', error)
        }
        transcriptionChannelNameRef.current = ''
      }
    }
  }, [user?.id]) // 移除sessions依赖，避免数据加载时清除订阅定时器

  // 专门处理转录订阅的useEffect
  useEffect(() => {
    // 只有在已经有会话订阅且有sessions数据时才创建转录订阅
    if (!user?.id || !channelNameRef.current || !sessions.length) {
      return
    }

    // 如果已经有转录订阅，不重复创建
    if (transcriptionChannelNameRef.current) {
      console.log('⚠️ 转录订阅已存在，跳过创建')
      return
    }

    try {
      const sessionIds = sessions.map(s => s.id)
      const transcriptionChannelName = `user-transcriptions-${user.id}-${Date.now()}`
      console.log('📡 创建转录订阅:', transcriptionChannelName, '监听会话数:', sessionIds.length)
      
      const transcriptionChannel = subscriptionManager.createTranscriptionChannel(
        transcriptionChannelName, 
        sessionIds, 
        handleTranscriptionChangeRef.current
      )
      
      if (transcriptionChannel) {
        transcriptionChannelNameRef.current = transcriptionChannelName
        console.log('✅ 转录订阅创建成功，频道名:', transcriptionChannelName)
      } else {
        console.error('❌ 转录订阅创建失败')
      }
    } catch (error) {
      console.error('创建转录订阅失败:', error)
    }
  }, [user?.id, sessions.length, channelNameRef.current])

  // 页面卸载时的额外清理
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (channelNameRef.current) {
        console.log('🔄 页面卸载前清理会话订阅:', channelNameRef.current)
        try {
          subscriptionManager.removeChannel(channelNameRef.current)
        } catch (error) {
          console.error('页面卸载清理会话订阅失败:', error)
        }
      }
      
      if (transcriptionChannelNameRef.current) {
        console.log('🔄 页面卸载前清理转录订阅:', transcriptionChannelNameRef.current)
        try {
          subscriptionManager.removeChannel(transcriptionChannelNameRef.current)
        } catch (error) {
          console.error('页面卸载清理转录订阅失败:', error)
        }
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [])

  // 创建新的录音会话
  const createSession = async (title: string, language: string = 'zh-CN') => {
    if (!apiClient || !user) return null

    try {
      console.log('🚀 创建新的录音会话:', { title, language })
      
      // 第一步：调用后端API创建会话（处理业务逻辑、缓存管理等）
      const response = await apiClient.createSession(title, language)
      console.log('✅ 后端会话创建成功:', response)
      
      // 适配新的响应格式
      const sessionData = response.data || response // 兼容新旧格式
      
      // 第二步：使用前端Supabase客户端触发一个UPDATE操作，确保实时订阅能接收到事件
      // 这个操作会触发UPDATE事件，从而让前端实时订阅感知到新会话
      const { data: updatedSession, error } = await supabase
        .from('recording_sessions')
        .update({ 
          updated_at: new Date().toISOString() // 只更新时间戳，触发UPDATE事件
        })
        .eq('id', sessionData.session_id)
        .select()
        .single()
      
      if (error) {
        console.warn('触发实时订阅更新失败，但会话已创建:', error)
      }
      
      const localSession: RecordingSessionWithRelations = {
        id: sessionData.session_id,
        user_id: user.id,
        title: sessionData.title,
        status: 'created',
        language: sessionData.language,
        metadata: {},
        created_at: sessionData.created_at,
        updated_at: updatedSession?.updated_at ? String(updatedSession.updated_at) : sessionData.created_at,
        duration_seconds: 0,
        audio_files: [],
        transcriptions: [],
        ai_summaries: []
      }
      
      // 立即添加到本地状态，确保界面能立即显示
      setSessions(prev => {
        // 检查是否已存在，避免重复添加
        if (prev.some(s => s.id === sessionData.session_id)) {
          return prev
        }
        return [localSession, ...prev]
      })
      
      // 延迟刷新数据以确保获取完整信息
      setTimeout(() => {
        if (user?.id) {
          console.log('🔄 刷新会话数据以确保一致性')
          fetchSessions(user.id)
        }
      }, 500)
      
      toast.success('创建录音会话成功')
      
      return {
        session_id: sessionData.session_id,
        session: localSession
      }
    } catch (error) {
      console.error('创建录音会话失败:', error)
      toast.error('创建录音会话失败')
      return null
    }
  }

  // 完成会话
  const finalizeSession = async (sessionId: string) => {
    console.log('🔍 finalizeSession 调试信息:', {
      sessionId,
      hasApiClient: !!apiClient,
      hasUser: !!user,
      userId: user?.id,
      hasSession: !!session,
      hasAccessToken: !!session?.access_token
    })
    
    if (!apiClient || !user) {
      console.error('❌ API客户端未初始化或用户未登录')
      return
    }

    try {
      console.log('🏁 完成会话:', sessionId)
      
      // 第一步：调用后端API完成会话（处理转录、音频文件、业务逻辑等）
      const result = await apiClient.finalizeSession(sessionId)
      console.log('✅ 后端会话完成:', result)
      
      // 第二步：使用前端Supabase客户端触发UPDATE事件，确保实时订阅能接收到状态更新
      const { data, error } = await supabase
        .from('recording_sessions')
        .update({ 
          status: 'completed',
          ended_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          duration_seconds: Math.floor(Number(result.final_data?.total_duration_seconds || 0))
        })
        .eq('id', sessionId)
        .select()
        .single()
      
      if (error) {
        console.warn('触发实时订阅更新失败，但会话已完成:', error)
      } else {
        console.log('✅ 实时订阅更新成功:', data)
      }
      
      // 延迟刷新数据，确保获取完整的转录和总结信息
      setTimeout(() => {
        if (user?.id) {
          console.log('🔄 刷新会话数据以获取最新信息')
          fetchSessions(user.id)
        }
      }, 1500)
      
      toast.success('会话已完成')
      return result
    } catch (error) {
      console.error('完成会话失败:', error)
      toast.error('完成会话失败')
      throw error
    }
  }

  // 更新会话状态
  const updateSessionStatus = async (sessionId: string, status: string) => {
    try {
      console.log('🔄 更新会话状态:', sessionId, '从', sessions.find(s => s.id === sessionId)?.status, '到', status)
      
      const updateData: any = { 
        status,
        updated_at: new Date().toISOString()
      }

      if (status === 'completed') {
        updateData.ended_at = new Date().toISOString()
      }

      const { data, error } = await supabase
        .from('recording_sessions')
        .update(updateData)
        .eq('id', sessionId)
        .select()
        .single()

      if (error) throw error

      console.log('✅ 会话状态更新成功:', data)
      
      // 实时订阅应该会自动处理UPDATE事件，但我们也立即更新本地状态确保一致性
      setSessions(prev => 
        prev.map(session => 
          session.id === sessionId 
            ? { ...session, ...data } 
            : session
        )
      )
    } catch (error) {
      console.error('更新会话状态失败:', error)
      toast.error('更新会话状态失败')
    }
  }

  // 更新会话标题
  const updateSessionTitle = async (sessionId: string, title: string) => {
    try {
      const { error } = await supabase
        .from('recording_sessions')
        .update({ 
          title,
          updated_at: new Date().toISOString()
        })
        .eq('id', sessionId)

      if (error) throw error

      setSessions(prev => 
        prev.map(session => 
          session.id === sessionId 
            ? { ...session, title } 
            : session
        )
      )
      toast.success('标题更新成功')
    } catch (error) {
      console.error('更新标题失败:', error)
      toast.error('更新标题失败')
    }
  }

  // 删除录音会话
  const deleteSession = async (sessionId: string) => {
    if (!apiClient) {
      console.error('❌ API客户端未初始化')
      toast.error('系统未初始化，请刷新页面')
      return
    }

    try {
      console.log('🗑️ 删除录音会话:', sessionId)
      
      // 调用后端API删除会话（包括音频文件）
      const response = await apiClient.deleteSession(sessionId)
      console.log('✅ 后端删除会话成功:', response)
      
      // 适配新的响应格式
      const result = response.data || response // 兼容新旧格式
      
      // 立即更新本地状态
      setSessions(prev => prev.filter(session => session.id !== sessionId))
      
      toast.success('删除录音会话成功')
    } catch (error) {
      console.error('删除录音会话失败:', error)
      
      // 提供更详细的错误信息
      if (error instanceof Error) {
        if (error.message.includes('404')) {
          toast.error('录音会话不存在或已被删除')
        } else if (error.message.includes('403')) {
          toast.error('无权删除此录音会话')
        } else {
          toast.error(`删除录音会话失败: ${error.message}`)
        }
      } else {
        toast.error('删除录音会话失败')
      }
    }
  }

  // 生成AI总结 - V2异步API
  const generateSummary = async (sessionId: string, transcription: string, templateId?: string) => {
    if (!apiClient) return null

    try {
      console.log('🤖 生成AI总结V2调试:', {
        sessionId, 
        templateId,
        templateIdType: typeof templateId,
        isTemplateIdString: typeof templateId === 'string',
        templateIdValue: templateId
      })
      
      // 调用V2异步API - 使用会话级总结API
      const result = await apiClient.generateSessionSummary(sessionId, true, templateId)
      
      console.log('✅ V2 AI总结生成并保存完成:', result)
      
      // 刷新会话数据以获取最新的总结
      const { data: { user: currentUser } } = await supabase.auth.getUser()
      if (currentUser?.id) {
        await fetchSessions(currentUser.id)
      }
      
      return {
        summary: result.summary,
        metadata: result.metadata
      }
    } catch (error) {
      console.error('生成V2 AI总结失败:', error)
      toast.error('生成AI总结失败')
      return null
    }
  }

  // 生成AI标题
  const generateTitle = async (sessionId: string, transcription: string, summary?: string) => {
    if (!apiClient) return null

    try {
      console.log('🤖 生成AI标题:', sessionId)
      
      const result = await apiClient.generateTitle(sessionId, transcription, summary)
      console.log('✅ AI标题生成完成:', result)
      
      await updateSessionTitle(sessionId, result.title)
      
      return result
    } catch (error) {
      console.error('生成AI标题失败:', error)
      toast.error('生成AI标题失败')
      return null
    }
  }

  return {
    sessions,
    loading,
    createSession,
    finalizeSession,
    updateSessionStatus,
    updateSessionTitle,
    deleteSession,
    generateSummary,
    generateTitle,
    fetchSessions: (force: boolean = false) => {
      if (user?.id) {
        fetchSessions(user.id, force)
      }
    }
  }
} 