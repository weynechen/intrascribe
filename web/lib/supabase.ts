import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

// 全局单例模式：确保只创建一个Supabase客户端实例
let supabaseInstance: ReturnType<typeof createClient> | null = null
let isCreating = false

function createSupabaseClient(): ReturnType<typeof createClient> {
  // 如果实例已存在，直接返回
  if (supabaseInstance) {
    return supabaseInstance
  }

  // 防止并发创建多个实例 - 简化处理
  if (isCreating) {
    // 如果正在创建，直接创建一个新的客户端实例
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

    console.log('🔗 Supabase客户端已初始化')
    return supabaseInstance
  } finally {
    isCreating = false
  }
}

// 导出单例实例
export const supabase = createSupabaseClient()

// 确保在全局范围内只有一个实例
if (typeof window !== 'undefined') {
  const globalWindow = window as { __supabase?: typeof supabase }
  if (!globalWindow.__supabase) {
    globalWindow.__supabase = supabase
  } else {
    console.warn('检测到已存在的Supabase实例，使用现有实例')
  }
}

// 页面刷新和卸载清理
if (typeof window !== 'undefined') {
  // 页面刷新前清理所有订阅
  window.addEventListener('beforeunload', () => {
    console.log('🔄 页面即将刷新，清理所有订阅')
    subscriptionManager.cleanupAllChannels()
  })
  
  // 页面隐藏时暂停订阅
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      console.log('📴 页面隐藏，暂停订阅活动')
    } else {
      console.log('👁️ 页面可见，恢复订阅活动')
    }
  })
}

// 全局订阅管理器，防止重复订阅
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
    // 检查是否已存在相同的订阅
    if (this.activeChannels.has(channelName)) {
      console.warn(`频道 ${channelName} 已存在，返回现有订阅`)
      return this.activeChannels.get(channelName)
    }

    try {
      console.log(`🔧 正在创建频道: ${channelName}, 用户ID: ${userId}`)
      console.log(`🔧 订阅配置: schema=public, table=recording_sessions, filter=user_id=eq.${userId}`)
      
      const channel = supabase
        .channel(channelName)
        .on('postgres_changes', {
          event: '*',
          schema: 'public',
          table: 'recording_sessions',
          filter: `user_id=eq.${userId}`
        }, (payload: RealtimePayload) => {
          // 防护措施：检查页面是否仍然可见
          if (typeof document !== 'undefined' && document.hidden) {
            console.log(`⏸️ 页面隐藏中，跳过实时事件处理: ${channelName}`)
            return
          }
          
          console.log(`🎯 频道 ${channelName} 收到实时事件:`, {
            eventType: payload.eventType,
            table: payload.table,
            schema: payload.schema,
            newId: payload.new?.id,
            oldId: payload.old?.id,
            newStatus: payload.new?.status,
            timestamp: new Date().toISOString()
          })
          
          try {
            callback(payload)
          } catch (error) {
            console.error(`❌ 处理实时事件回调失败:`, error)
          }
        })
        .subscribe((status: string) => {
          console.log(`📡 频道 ${channelName} 订阅状态变化:`, status)
          if (status === 'SUBSCRIBED') {
            console.log(`✅ 频道 ${channelName} 订阅成功`)
          } else if (status === 'CHANNEL_ERROR') {
            console.error(`❌ 频道 ${channelName} 订阅失败`)
            // 订阅失败时自动清理
            this.removeChannel(channelName)
          } else if (status === 'TIMED_OUT') {
            console.error(`⏰ 频道 ${channelName} 订阅超时`)
            // 超时时自动清理并重试
            this.removeChannel(channelName)
          } else if (status === 'CLOSED') {
            console.log(`🔒 频道 ${channelName} 订阅已关闭`)
            // 确保从映射中移除
            this.activeChannels.delete(channelName)
          }
        })

      this.activeChannels.set(channelName, channel)
      console.log(`✅ 创建新频道: ${channelName}`)
      return channel
    } catch (error) {
      console.error(`创建频道失败: ${channelName}`, error)
      return null
    }
  },

  // 创建转录表订阅频道
  createTranscriptionChannel(channelName: string, sessionIds: string[], callback: (payload: RealtimePayload) => void) {
    // 检查是否已存在相同的订阅
    if (this.activeChannels.has(channelName)) {
      console.warn(`转录频道 ${channelName} 已存在，返回现有订阅`)
      return this.activeChannels.get(channelName)
    }

    try {
      console.log(`🔧 正在创建转录频道: ${channelName}, 监听会话IDs: ${sessionIds.slice(0, 3)}...`)
      
      const channel = supabase
        .channel(channelName)
        .on('postgres_changes', {
          event: '*',
          schema: 'public',
          table: 'transcriptions'
        }, (payload: RealtimePayload) => {
          // 防护措施：检查页面是否仍然可见
          if (typeof document !== 'undefined' && document.hidden) {
            console.log(`⏸️ 页面隐藏中，跳过转录实时事件处理: ${channelName}`)
            return
          }

          // 检查是否是我们关心的会话的转录更新
          const sessionId = payload.new?.session_id || payload.old?.session_id
          if (sessionId && typeof sessionId === 'string' && sessionIds.includes(sessionId)) {
            console.log(`🎯 转录频道 ${channelName} 收到相关实时事件:`, {
              eventType: payload.eventType,
              table: payload.table,
              sessionId: sessionId,
              transcriptionId: payload.new?.id || payload.old?.id,
              timestamp: new Date().toISOString()
            })
            
            try {
              callback(payload)
            } catch (error) {
              console.error(`❌ 处理转录实时事件回调失败:`, error)
            }
          } else {
            console.log(`🔍 转录事件不匹配当前会话，跳过处理`, {
              eventSessionId: sessionId,
              targetSessionIds: sessionIds.slice(0, 3)
            })
          }
        })
        .subscribe((status: string) => {
          console.log(`📡 转录频道 ${channelName} 订阅状态变化:`, status)
          if (status === 'SUBSCRIBED') {
            console.log(`✅ 转录频道 ${channelName} 订阅成功`)
          } else if (status === 'CHANNEL_ERROR') {
            console.error(`❌ 转录频道 ${channelName} 订阅失败`)
            this.removeChannel(channelName)
          } else if (status === 'TIMED_OUT') {
            console.error(`⏰ 转录频道 ${channelName} 订阅超时`)
            this.removeChannel(channelName)
          } else if (status === 'CLOSED') {
            console.log(`🔒 转录频道 ${channelName} 订阅已关闭`)
            this.activeChannels.delete(channelName)
          }
        })

      this.activeChannels.set(channelName, channel)
      console.log(`✅ 创建新转录频道: ${channelName}`)
      return channel
    } catch (error) {
      console.error(`创建转录频道失败: ${channelName}`, error)
      return null
    }
  },

  removeChannel(channelName: string) {
    const channel = this.activeChannels.get(channelName)
    if (channel) {
      try {
        console.log(`🔄 正在移除频道: ${channelName}`)
        channel.unsubscribe()
        this.activeChannels.delete(channelName)
        console.log(`🗑️ 移除频道成功: ${channelName}`)
      } catch (error) {
        console.error(`移除频道失败: ${channelName}`, error)
        // 即使unsubscribe失败，也要从映射中移除
        this.activeChannels.delete(channelName)
      }
    } else {
      console.log(`⚠️ 频道不存在，无需移除: ${channelName}`)
    }
  },

  // 清理所有频道
  cleanupAllChannels() {
    const channelNames = Array.from(this.activeChannels.keys())
    console.log(`🧹 清理所有频道，共 ${channelNames.length} 个`)
    
    channelNames.forEach(channelName => {
      this.removeChannel(channelName)
    })
    
    // 强制清空映射
    this.activeChannels.clear()
    console.log('✅ 所有频道清理完成')
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

// API 响应类型
export interface SessionCreateResponse {
  session_id: string
  title: string
  status: string
  created_at: string
  language: string
  usage_hint: string
}

export interface SessionFinalizeResponse {
  message: string
  session_id: string
  status: string
  final_data: {
    total_duration_seconds: number
    word_count: number
    audio_file_path: string
    transcription_saved: boolean
  }
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
export interface AISummaryResponse {
  summary: string
  metadata: {
    model_used: string
    success: boolean
    total_processing_time: number
    transcription_length: number
    timestamp: number
    error?: string
    fallback_used?: boolean
  }
}

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
    
    console.log('🌐 API请求调试:', {
      url,
      method: options.method || 'GET',
      hasToken: !!token,
      tokenPreview: token ? `${token.substring(0, 20)}...` : null
    })
    
    const config: RequestInit = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
    }

    const response = await fetch(url, config)
    
    console.log('📡 API响应调试:', {
      url,
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
    return this.request<SessionCreateResponse>('/sessions', {
      method: 'POST',
      body: JSON.stringify({
        title,
        language,
        stt_model: sttModel
      })
    })
  }

  async finalizeSession(sessionId: string): Promise<SessionFinalizeResponse> {
    return this.request<SessionFinalizeResponse>(`/sessions/${sessionId}/finalize`, {
      method: 'POST'
    })
  }

  async deleteSession(sessionId: string): Promise<{ message: string; session_id: string; deleted: boolean }> {
    return this.request<{ message: string; session_id: string; deleted: boolean }>(`/sessions/${sessionId}`, {
      method: 'DELETE'
    })
  }

  async getSession(sessionId: string): Promise<RecordingSession> {
    return this.request<RecordingSession>(`/sessions/${sessionId}`)
  }

  // AI 服务
  async generateSummary(transcription: string): Promise<AISummaryResponse> {
    return this.request<AISummaryResponse>('/summarize', {
      method: 'POST',
      body: JSON.stringify({ transcription })
    })
  }

  async generateSessionSummary(sessionId: string, force: boolean = false, templateId?: string): Promise<{ summary: string; metadata: Record<string, unknown> }> {
    console.log('🌐 APIClient.generateSessionSummary调试:', {
      sessionId,
      force,
      templateId,
      templateIdType: typeof templateId,
      isTemplateIdString: typeof templateId === 'string'
    })
    
    const params = new URLSearchParams()
    if (force) params.append('force', 'true')
    if (templateId) params.append('template_id', templateId)
    
    const queryString = params.toString()
    console.log('🌐 生成的URL查询字符串:', queryString)
    
    return this.request<{ summary: string; metadata: Record<string, unknown> }>(`/sessions/${sessionId}/summarize${queryString ? `?${queryString}` : ''}`, {
      method: 'POST'
    })
  }

  async generateTitle(transcription: string, summary?: string): Promise<AITitleResponse> {
    return this.request<AITitleResponse>('/generate-title', {
      method: 'POST',
      body: JSON.stringify({
        transcription,
        ...(summary && { summary })
      })
    })
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
    return this.request<SummaryTemplate[]>('/templates')
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
  async updateSessionTemplate(sessionId: string, templateId: string): Promise<{ message: string; session_id: string; template_id: string }> {
    return this.request<{ message: string; session_id: string; template_id: string }>(`/sessions/${sessionId}/template`, {
      method: 'PUT',
      body: JSON.stringify({ template_id: templateId })
    })
  }

  // 重新转录会话
  async retranscribeSession(sessionId: string): Promise<{ success: boolean; message: string; session_id: string; status: string }> {
    return this.request<{ success: boolean; message: string; session_id: string; status: string }>(`/sessions/${sessionId}/retranscribe`, {
      method: 'POST'
    })
  }
} 