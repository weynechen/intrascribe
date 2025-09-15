import { createClient } from '@supabase/supabase-js'
import {
  TaskStatusResponse, SessionData,
  SessionCreateResponse, SessionDeleteResponse, SessionFinalizeResponse,
  AISummaryResponse,
  isSyncResponse,
  getTaskStatus
} from './api-types'

// Always use Next.js proxy, works with both HTTP and HTTPS
const supabaseUrl = typeof window !== 'undefined' 
  ? `${window.location.origin}/supabase`  // Browser environment: use current domain + proxy path
  : 'http://localhost:3000/supabase'      // Server environment: use local address + proxy path

const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

if (!supabaseAnonKey) {
  throw new Error('Missing NEXT_PUBLIC_SUPABASE_ANON_KEY environment variable')
}

// Global singleton pattern: ensure only one Supabase client instance is created
let supabaseInstance: ReturnType<typeof createClient> | null = null
let isCreating = false

function createSupabaseClient(): ReturnType<typeof createClient> {
  // If instance already exists, return directly
  if (supabaseInstance) {
    return supabaseInstance
  }

  // Prevent concurrent creation of multiple instances - simplified handling
  if (isCreating) {
    // If currently creating, directly create a new client instance
    return createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
        storage: typeof window !== 'undefined' ? window.localStorage : undefined,
        storageKey: 'intrascribe-auth',
        flowType: 'pkce'
      }
    })
  }

  isCreating = true

  try {
    supabaseInstance = createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
        storage: typeof window !== 'undefined' ? window.localStorage : undefined,
        storageKey: 'intrascribe-auth',
        flowType: 'pkce'
      },
      realtime: {
        params: {
          eventsPerSecond: 10
        }
      },
      global: {
        headers: {
          'x-client-info': 'intrascribe-web@1.0.0'
        }
      }
    })

    return supabaseInstance
  } finally {
    isCreating = false
  }
}

// Export singleton instance
export const supabase = createSupabaseClient()

// Ensure only one instance globally
if (typeof window !== 'undefined') {
  const globalWindow = window as { __supabase?: typeof supabase }
  if (!globalWindow.__supabase) {
    globalWindow.__supabase = supabase
  } else {
  }
}

// Page refresh and unload cleanup
if (typeof window !== 'undefined') {
  // Clean up all subscriptions before page refresh
  window.addEventListener('beforeunload', () => {
    subscriptionManager.cleanupAllChannels()
  })
  
  // Pause subscriptions when page is hidden
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
    } else {
    }
  })
}

// Global subscription manager to prevent duplicate subscriptions
interface RealtimePayload {
  eventType: string
  table: string
  schema: string
  new?: Record<string, unknown>
  old?: Record<string, unknown>
}

const subscriptionManager = {
  activeChannels: new Map<string, ReturnType<typeof supabase.channel>>(),
  
  createChannel(channelName: string, userId: string, callback: (payload: RealtimePayload) => void) {
    // Check if the same subscription already exists
    if (this.activeChannels.has(channelName)) {
      return this.activeChannels.get(channelName)
    }

    try {
      
      const channel = supabase
        .channel(channelName)
        .on('postgres_changes', {
          event: '*',
          schema: 'public',
          table: 'recording_sessions',
          filter: `user_id=eq.${userId}`
        }, (payload: RealtimePayload) => {
          // Safety measure: check if page is still visible
          if (typeof document !== 'undefined' && document.hidden) {
            return
          }
          
          
          try {
            callback(payload)
          } catch (error) {
          }
        })
        .subscribe((status: string) => {
          if (status === 'SUBSCRIBED') {
          } else if (status === 'CHANNEL_ERROR') {
            // Auto cleanup on subscription failure
            this.removeChannel(channelName)
          } else if (status === 'TIMED_OUT') {
            // Auto cleanup and retry on timeout
            this.removeChannel(channelName)
          } else if (status === 'CLOSED') {
            // Ensure removal from mapping
            this.activeChannels.delete(channelName)
          }
        })

      this.activeChannels.set(channelName, channel)
      return channel
    } catch (error) {
      return null
    }
  },

  // Create transcription table subscription channel
  createTranscriptionChannel(channelName: string, sessionIds: string[], callback: (payload: RealtimePayload) => void) {
    // Check if the same subscription already exists
    if (this.activeChannels.has(channelName)) {
      return this.activeChannels.get(channelName)
    }

    try {
      
      const channel = supabase
        .channel(channelName)
        .on('postgres_changes', {
          event: '*',
          schema: 'public',
          table: 'transcriptions'
        }, (payload: RealtimePayload) => {
          // Safety measure: check if page is still visible
          if (typeof document !== 'undefined' && document.hidden) {
            return
          }

          // Check if it's a transcription update for sessions we care about
          const sessionId = payload.new?.session_id || payload.old?.session_id
          if (sessionId && typeof sessionId === 'string' && sessionIds.includes(sessionId)) {
            
            try {
              callback(payload)
            } catch (error) {
            }
          } else {
          }
        })
        .subscribe((status: string) => {
          if (status === 'SUBSCRIBED') {
          } else if (status === 'CHANNEL_ERROR') {
            this.removeChannel(channelName)
          } else if (status === 'TIMED_OUT') {
            this.removeChannel(channelName)
          } else if (status === 'CLOSED') {
            this.activeChannels.delete(channelName)
          }
        })

      this.activeChannels.set(channelName, channel)
      return channel
    } catch (error) {
      return null
    }
  },

  removeChannel(channelName: string) {
    const channel = this.activeChannels.get(channelName)
    if (channel) {
      try {
        channel.unsubscribe()
        this.activeChannels.delete(channelName)
      } catch (error) {
        // Remove from mapping even if unsubscribe fails
        this.activeChannels.delete(channelName)
      }
    } else {
    }
  },

  // Clean up all channels
  cleanupAllChannels() {
    const channelNames = Array.from(this.activeChannels.keys())
    
    channelNames.forEach(channelName => {
      this.removeChannel(channelName)
    })
    
    // Force clear mapping
    this.activeChannels.clear()
  },

  getActiveChannels() {
    return Array.from(this.activeChannels.keys())
  },

  // 获取活跃频道数量
  getActiveChannelCount() {
    return this.activeChannels.size
  },

  // 检查特定频道是否存在
  hasChannel(channelName: string) {
    return this.activeChannels.has(channelName)
  },

  // 获取订阅状态信息
  getSubscriptionInfo() {
    const info = {
      totalChannels: this.activeChannels.size,
      channels: Array.from(this.activeChannels.entries()).map(([name]) => ({
        name,
        status: 'active'
      })),
      timestamp: new Date().toISOString()
    }
    
    console.log('📊 当前订阅状态:', info)
    return info
  },

  // 健康检查
  healthCheck() {
    const activeChannels = this.getActiveChannels()
    const now = Date.now()
    
    console.log('🏥 订阅健康检查:', {
      activeChannelCount: activeChannels.length,
      channels: activeChannels,
      timestamp: new Date().toISOString()
    })
    
    // 检查是否有过期的订阅（超过1小时的订阅）
    activeChannels.forEach(channelName => {
      const parts = channelName.split('-')
      const timestamp = parts[parts.length - 1]
      if (timestamp && !isNaN(Number(timestamp))) {
        const age = now - Number(timestamp)
        const hours = age / (1000 * 60 * 60)
        
        if (hours > 1) {
          console.warn(`⚠️ 发现过期订阅: ${channelName}, 存在时间: ${hours.toFixed(2)}小时`)
          // 可以选择自动清理过期订阅
          // this.removeChannel(channelName)
        }
      }
    })
    
    return {
      healthy: activeChannels.length < 10, // 假设超过10个订阅为异常
      activeChannels: activeChannels.length,
      channels: activeChannels
    }
  }
}

// 在开发环境中暴露订阅管理器用于调试
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  const globalWindow = window as { 
    __subscriptionManager?: typeof subscriptionManager
    __debugSupabase?: {
      getSubscriptionInfo: () => ReturnType<typeof subscriptionManager.getSubscriptionInfo>
      healthCheck: () => ReturnType<typeof subscriptionManager.healthCheck>
      cleanupAll: () => void
      getActiveChannels: () => ReturnType<typeof subscriptionManager.getActiveChannels>
    }
  }
  globalWindow.__subscriptionManager = subscriptionManager
  
  // 开发环境下定期进行健康检查
  setInterval(() => {
    const health = subscriptionManager.healthCheck()
    if (!health.healthy) {
      console.warn('⚠️ 订阅健康检查失败:', health)
    }
  }, 5 * 60 * 1000) // 每5分钟检查一次
  
  // 提供调试命令
  globalWindow.__debugSupabase = {
    getSubscriptionInfo: () => subscriptionManager.getSubscriptionInfo(),
    healthCheck: () => subscriptionManager.healthCheck(),
    cleanupAll: () => subscriptionManager.cleanupAllChannels(),
    getActiveChannels: () => subscriptionManager.getActiveChannels()
  }
  
  console.log('🔧 开发环境调试工具已加载，使用 window.__debugSupabase 访问')
}

export { subscriptionManager }

// 数据库类型定义
export interface User {
  id: string
  email: string
  username: string
  full_name?: string
  avatar_url?: string
  created_at: string
  updated_at: string
}

export interface RecordingSession {
  id: string
  user_id: string
  title: string
  description?: string
  status: 'created' | 'recording' | 'processing' | 'completed' | 'failed' | 'cancelled'
  language: string
  stt_model?: string
  template_id?: string
  started_at?: string
  ended_at?: string
  duration_seconds?: number
  metadata: Record<string, unknown>
  tags?: string[]
  created_at: string
  updated_at: string
}

export interface AudioFile {
  id: string
  session_id: string
  user_id: string
  original_filename?: string
  storage_path: string
  storage_bucket: string
  public_url?: string
  file_size_bytes: number
  duration_seconds?: number
  format: string
  mime_type?: string
  sample_rate?: number
  bit_rate?: number
  channels: number
  encoding?: string
  upload_status: 'uploading' | 'completed' | 'failed'
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  file_hash?: string
  quality_level?: string
  metadata: Record<string, unknown>
  is_public: boolean
  access_level: 'private' | 'shared' | 'public'
  created_at: string
  updated_at: string
}

export interface Transcription {
  id: string
  session_id: string
  content: string
  segments: unknown[]
  language: string
  confidence_score?: number
  processing_time_ms?: number
  stt_model?: string
  stt_version?: string
  status: 'processing' | 'completed' | 'failed'
  quality_score?: number
  word_count?: number
  created_at: string
  updated_at: string
}

export interface AISummary {
  id: string
  session_id: string
  transcription_id: string
  summary: string
  key_points: unknown[]
  action_items: unknown[]
  participants: unknown[]
  ai_model: string
  ai_provider?: string
  model_version?: string
  processing_time_ms?: number
  token_usage: Record<string, unknown>
  cost_cents?: number
  status: 'processing' | 'completed' | 'failed'
  quality_rating?: number
  template_id?: string
  created_at: string
  updated_at: string
}

// 扩展的会话接口，包含关联数据
export interface RecordingSessionWithRelations extends RecordingSession {
  audio_files?: AudioFile[]
  transcriptions?: Transcription[]
  ai_summaries?: AISummary[]
}

// Local session data interface for legacy compatibility
interface LocalSessionCreateResponse {
  session_id: string
  title: string
  status: string
  created_at: string
  language: string
  usage_hint: string
}


// 实时转录数据类型
export interface TranscriptEvent {
  index: number
  speaker: string
  timestamp: string
  text: string
  is_final: boolean
}

// AI 服务响应类型

export interface AITitleResponse {
  title: string
  metadata: {
    model_used: string
    success: boolean
    total_processing_time: number
    transcription_length: number
    summary_provided?: boolean
    timestamp: number
    error?: string
    fallback_used?: boolean
  }
}

// 模板相关类型
export interface SummaryTemplate {
  id: string
  name: string
  description?: string
  template_content: string
  category: string
  is_default: boolean
  is_active: boolean
  usage_count: number
  tags: string[]
  created_at: string
  updated_at: string
}

export interface CreateTemplateRequest {
  name: string
  description?: string
  template_content: string
  category?: string
  is_default?: boolean
  is_active?: boolean
  tags?: string[]
}

// API 客户端类
export class APIClient {
  private baseURL: string
  private getAuthToken: () => string | null

  constructor(baseURL: string = '/api/v1', getAuthToken: () => string | null) {
    this.baseURL = baseURL
    this.getAuthToken = getAuthToken
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getAuthToken()
    const url = `${this.baseURL}${endpoint}`
    
    // 确保URL是相对路径，强制通过Next.js代理
    const finalUrl = url.startsWith('/') ? url : `/${url}`
    
    console.log('🌐 API请求调试:', {
      originalUrl: url,
      finalUrl,
      method: options.method || 'GET',
      hasToken: !!token,
      tokenPreview: token ? `${token.substring(0, 20)}...` : null,
      tokenLength: token ? token.length : 0,
      endpoint,
      baseURL: this.baseURL,
      windowOrigin: typeof window !== 'undefined' ? window.location.origin : 'server-side'
    })
    
    const config: RequestInit = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
    }

    const response = await fetch(finalUrl, config)
    
    console.log('📡 API响应调试:', {
      requestedUrl: finalUrl,
      responseUrl: response.url,
      status: response.status,
      statusText: response.statusText,
      ok: response.ok
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      console.error('❌ API错误详情:', error)
      throw new Error(error.error?.message || `HTTP ${response.status}`)
    }

    return response.json()
  }

  // 会话管理
  async createSession(title: string, language: string = 'zh-CN', sttModel: string = 'whisper'): Promise<SessionCreateResponse> {
    const response = await this.request<LocalSessionCreateResponse>('/sessions', {
      method: 'POST',
      body: JSON.stringify({
        title,
        language,
        stt_model: sttModel
      })
    })
    
    // 检查响应格式并适配
    if (isSyncResponse(response)) {
      // 新的统一响应格式
      return response as SessionCreateResponse
    } else {
      // 兼容旧格式，包装成新格式
      return {
        success: true,
        message: "会话创建成功",
        timestamp: new Date().toISOString(),
        data: response as SessionData
      }
    }
  }

  async finalizeSession(sessionId: string): Promise<SessionFinalizeResponse> {
    // 使用V2 API - 直接处理同步响应
    const baseURL = this.baseURL.replace('/v1', '') // 移除v1，直接访问v2
    
    const response = await fetch(`${baseURL}/v2/sessions/${sessionId}/finalize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.getAuthToken()}`
      }
    })

    if (!response.ok) {
      throw new Error(`会话结束失败: ${response.status}`)
    }

    const data = await response.json()
    console.log('✅ V2会话结束完成:', data)

    // 检查是否是异步任务响应
    if (data.task_id && data.status === "started") {
      // 异步任务，需要轮询
      const result = await this.pollV2TaskStatus(data.task_id)
      return {
        message: "Session finalized successfully.",
        session_id: sessionId,
        status: "completed",
        final_data: result
      }
    } else {
      // 同步响应，直接返回
      return {
        message: data.message || "Session finalized successfully.",
        session_id: sessionId,
        status: "completed",
        final_data: data.result || {
          total_duration_seconds: 0,
          transcription_saved: true
        }
      }
    }
  }

  async deleteSession(sessionId: string): Promise<SessionDeleteResponse> {
    const response = await this.request<SessionDeleteResponse>(`/sessions/${sessionId}`, {
      method: 'DELETE'
    })
    
    // 检查响应格式并适配
    if (isSyncResponse(response)) {
      // 新的统一响应格式
      return response
    } else {
      // 兼容旧格式，包装成新格式
      return {
        success: true,
        message: "会话删除成功",
        timestamp: new Date().toISOString(),
        data: {
          session_id: sessionId,
          deleted: true
        }
      }
    }
  }

  async getSession(sessionId: string): Promise<RecordingSession> {
    return this.request<RecordingSession>(`/sessions/${sessionId}`)
  }

  // 响应格式检测和处理
  private isAsyncResponse(response: unknown): boolean {
    return typeof response === 'object' && 
           response !== null && 
           'task_id' in response && 'poll_url' in response
  }
  
  private isSyncResponse(response: unknown): boolean {
    return typeof response === 'object' && 
           response !== null && 
           'data' in response && !('task_id' in response)
  }

  // AI 服务 - 统一响应处理
  async generateSummary(transcription: string, sessionId: string, templateId?: string): Promise<AISummaryResponse> {
    // 调用基于session的summarize API
    const baseURL = this.baseURL.replace('/v1', '') // 移除v1，直接访问v2
    
    const response = await fetch(`${baseURL}/v2/sessions/${sessionId}/summarize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.getAuthToken()}`
      },
      body: JSON.stringify({
        transcription_text: transcription,
        ...(templateId && { template_id: templateId })
      })
    })
    
    if (!response.ok) {
      throw new Error(`Summary generation failed: ${response.status}`)
    }
    
    const data = await response.json()
    
    // 检查是否是异步响应
    if (this.isAsyncResponse(data)) {
      console.log('🔄 检测到异步响应，开始轮询:', data.task_id)
      const result = await this.pollV2TaskStatus(data.task_id)
      const summaryResult = result as { summary: string; key_points?: string[]; metadata?: Record<string, unknown> }
      return {
        summary: summaryResult.summary,
        key_points: summaryResult.key_points || [],
        metadata: summaryResult.metadata || {}
      }
    } else {
      // 直接返回同步响应
      console.log('✅ 收到同步响应')
      return {
        summary: data.summary,
        key_points: data.key_points || [],
        metadata: data.metadata || {}
      }
    }
  }

  // 轮询V2任务状态的辅助方法
  private async pollV2TaskStatus(taskId: string, maxAttempts: number = 120): Promise<unknown> {
    const baseURL = this.baseURL.replace('/v1', '') // 移除v1，直接访问v2
    
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const response = await fetch(`${baseURL}/v2/tasks/${taskId}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${this.getAuthToken()}`
          }
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const taskStatusResponse: TaskStatusResponse = await response.json()
        console.log(`🔄 V2任务状态轮询 ${attempt + 1}/${maxAttempts}:`, taskStatusResponse.status)

        // 使用新的类型守卫和工具函数
        const status = getTaskStatus(taskStatusResponse)
        
        // 任务完成
        if (status.isCompleted && taskStatusResponse.result) {
          console.log('✅ V2任务完成，返回结果')
          return taskStatusResponse.result
        }

        // 任务失败
        if (status.isFailed) {
          console.error('❌ V2任务失败:', taskStatusResponse.error)
          throw new Error(taskStatusResponse.error || '任务执行失败')
        }

        // 任务被取消
        if (status.isCancelled) {
          console.warn('⚠️ V2任务被取消')
          throw new Error('任务被取消')
        }

        // 任务仍在进行中
        if (status.isPending) {
          console.log('⏳ V2任务进行中:', taskStatusResponse.progress)
          await new Promise(resolve => setTimeout(resolve, 3000))
          continue
        }
        
        console.warn('⚠️ 未知任务状态:', taskStatusResponse.status)
        
      } catch (error) {
        console.error(`❌ V2任务状态查询失败 (第${attempt + 1}次):`, error)
        
        // 如果是认证错误，立即重试而不是等待太多次
        if (error instanceof Error && error.message.includes('403')) {
          console.warn('🔑 检测到认证错误，快速重试...')
          if (attempt >= 5) { // 认证错误只重试5次
            throw new Error(`认证失败，请重新登录: ${error.message}`)
          }
          await new Promise(resolve => setTimeout(resolve, 1000)) // 认证错误时短暂等待
          continue
        }
        
        // 其他错误的处理：最后几次尝试时抛出错误
        if (attempt >= maxAttempts - 3) {
          throw error
        }
        
        // 等待后重试
        await new Promise(resolve => setTimeout(resolve, 3000))
      }
    }

    throw new Error(`V2任务轮询超时 (${maxAttempts} 次尝试)`)
  }

  async generateSessionSummary(sessionId: string, force: boolean = false, templateId?: string): Promise<{ summary: string; metadata: Record<string, unknown> }> {
    console.log('🌐 APIClient.generateSessionSummary V2调试:', {
      sessionId,
      force,
      templateId,
      templateIdType: typeof templateId,
      isTemplateIdString: typeof templateId === 'string'
    })
    
    try {
      const baseURL = this.baseURL.replace('/v1', '') // 移除v1，直接访问v2
      const token = this.getAuthToken()
      
      console.log('🔑 认证调试:', {
        hasToken: !!token,
        tokenPreview: token ? `${token.substring(0, 20)}...` : null
      })
      
      if (!token) {
        throw new Error('用户未认证，无法生成AI总结')
      }
      
      // 直接提交V2异步任务，不需要先获取session（避免额外的API调用和认证问题）
      const taskResponse = await fetch(`${baseURL}/v2/sessions/${sessionId}/ai-summary`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          template_id: templateId || null
        })
      })

      console.log('📡 AI总结任务提交响应:', {
        status: taskResponse.status,
        statusText: taskResponse.statusText,
        ok: taskResponse.ok
      })

      if (!taskResponse.ok) {
        const errorData = await taskResponse.json().catch(() => ({}))
        console.error('❌ 提交AI总结任务失败:', errorData)
        throw new Error(`提交AI总结任务失败: ${taskResponse.status} - ${errorData.detail || taskResponse.statusText}`)
      }

      const taskData = await taskResponse.json()
      console.log('✅ V2 AI总结任务已提交:', taskData.task_id)

      // 轮询任务状态
      const result = await this.pollV2TaskStatus(taskData.task_id)
      console.log('✅ V2 AI总结生成完成')
      
      const summaryResult = result as { summary: string }
      return {
        summary: summaryResult.summary,
        metadata: { generated_by: 'v2_async_task' }
      }
    } catch (error) {
      console.error('V2 AI总结生成失败:', error)
      throw error
    }
  }

  async generateTitle(sessionId: string, transcription: string, summary?: string): Promise<AITitleResponse> {
    // 调用基于session的generate-title API
    const baseURL = this.baseURL.replace('/v1', '') // 移除v1，直接访问v2
    
    const response = await fetch(`${baseURL}/v2/sessions/${sessionId}/generate-title`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.getAuthToken()}`
      },
      body: JSON.stringify({
        transcription_text: transcription,
        summary_text: summary
      })
    })
    
    if (!response.ok) {
      throw new Error(`Title generation failed: ${response.status}`)
    }
    
    return response.json()
  }

  // 转录管理
  async updateTranscription(transcriptionId: string, segments: unknown[]): Promise<Transcription> {
    return this.request<Transcription>(`/transcriptions/${transcriptionId}`, {
      method: 'PUT',
      body: JSON.stringify({
        segments
      })
    })
  }

  // 模板管理
  async getTemplates(): Promise<SummaryTemplate[]> {
    const token = this.getAuthToken()
    
    console.log('🔑 模板加载认证调试:', {
      hasToken: !!token,
      tokenPreview: token ? `${token.substring(0, 20)}...` : null,
      tokenLength: token ? token.length : 0,
      baseURL: this.baseURL
    })
    
    if (!token) {
      throw new Error('用户未认证，无法加载模板')
    }
    
    return this.request<SummaryTemplate[]>('/templates/')
  }

  async createTemplate(template: CreateTemplateRequest): Promise<SummaryTemplate> {
    return this.request<SummaryTemplate>('/templates', {
      method: 'POST',
      body: JSON.stringify(template)
    })
  }

  async updateTemplate(templateId: string, template: Partial<CreateTemplateRequest>): Promise<SummaryTemplate> {
    return this.request<SummaryTemplate>(`/templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(template)
    })
  }

  async deleteTemplate(templateId: string): Promise<{ message: string; template_id: string }> {
    return this.request<{ message: string; template_id: string }>(`/templates/${templateId}`, {
      method: 'DELETE'
    })
  }

  async getTemplate(templateId: string): Promise<SummaryTemplate> {
    return this.request<SummaryTemplate>(`/templates/${templateId}`)
  }

  // 更新会话模板选择
  async updateSessionTemplate(sessionId: string, templateId: string | null): Promise<{ message: string; session_id: string; template_id: string }> {
    // 转换空字符串为null，避免后端UUID错误
    const finalTemplateId = (!templateId || templateId === '' || templateId === 'no-template') ? null : templateId
    
    console.log('🔧 updateSessionTemplate调试:', {
      original: templateId,
      final: finalTemplateId,
      originalType: typeof templateId,
      finalType: typeof finalTemplateId
    })
    
    return this.request<{ message: string; session_id: string; template_id: string }>(`/sessions/${sessionId}/template`, {
      method: 'PUT',
      body: JSON.stringify({ template_id: finalTemplateId })
    })
  }

  // 重新转录会话
  async retranscribeSession(sessionId: string): Promise<{ success: boolean; message: string; session_id: string; status: string; task_id?: string }> {
    try {
      // 使用V2异步API - 返回task_id
      const baseURL = this.baseURL.replace('/v1', '') // 移除v1，直接访问v2
      
      const taskResponse = await fetch(`${baseURL}/v2/sessions/${sessionId}/retranscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.getAuthToken()}`
        }
      })

      if (!taskResponse.ok) {
        throw new Error(`重新转录失败: ${taskResponse.status}`)
      }

      const taskData = await taskResponse.json()
      console.log('✅ V2重新转录任务已提交:', taskData.task_id)

      // 启动异步轮询，但不等待完成就返回
      this.pollV2TaskStatus(taskData.task_id).then(result => {
        console.log('✅ V2重新转录完成:', result)
        
        // 重新转录完成后，触发全局事件来通知前端更新
        if (typeof window !== 'undefined') {
          const event = new CustomEvent('retranscriptionCompleted', {
            detail: { sessionId, result }
          })
          window.dispatchEvent(event)
          console.log('🔔 触发重新转录完成事件:', { sessionId, result })
        }
      }).catch(error => {
        console.error('❌ V2重新转录失败:', error)
      })

      // 立即返回任务信息
      return {
        success: true,
        message: "重新转录任务已提交，正在后台处理",
        session_id: sessionId,
        status: "processing",
        task_id: taskData.task_id
      }
      
    } catch (error) {
      console.error('重新转录API调用失败，回退到V1:', error)
      
      // 回退到V1同步API（如果V2不可用）
      try {
        return await this.request<{ success: boolean; message: string; session_id: string; status: string }>(`/sessions/${sessionId}/retranscribe`, {
          method: 'POST'
        })
      } catch (error) {
        console.warn('V1 retranscribe API also failed:', error)
        return {
          success: false,
          message: "重新转录功能暂时不可用",
          session_id: sessionId,
          status: "failed"
        }
      }
    }
  }
} 