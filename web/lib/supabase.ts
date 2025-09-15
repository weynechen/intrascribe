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
    
    console.log('Current subscription status:', info)
    return info
  },

  // Health check
  healthCheck() {
    const activeChannels = this.getActiveChannels()
    const now = Date.now()
    
    console.log('Subscription health check:', {
      activeChannelCount: activeChannels.length,
      channels: activeChannels,
      timestamp: new Date().toISOString()
    })
    
    // Check for expired subscriptions (subscriptions older than 1 hour)
    activeChannels.forEach(channelName => {
      const parts = channelName.split('-')
      const timestamp = parts[parts.length - 1]
      if (timestamp && !isNaN(Number(timestamp))) {
        const age = now - Number(timestamp)
        const hours = age / (1000 * 60 * 60)
        
        if (hours > 1) {
          console.warn(`Found expired subscription: ${channelName}, age: ${hours.toFixed(2)} hours`)
          // Can choose to auto-cleanup expired subscriptions
          // this.removeChannel(channelName)
        }
      }
    })
    
    return {
      healthy: activeChannels.length < 10, // Assume more than 10 subscriptions is abnormal
      activeChannels: activeChannels.length,
      channels: activeChannels
    }
  }
}

// Expose subscription manager for debugging in development environment
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
  
  // Periodic health checks in development environment
  setInterval(() => {
    const health = subscriptionManager.healthCheck()
    if (!health.healthy) {
      console.warn('Subscription health check failed:', health)
    }
  }, 5 * 60 * 1000) // Check every 5 minutes
  
  // Provide debug commands
  globalWindow.__debugSupabase = {
    getSubscriptionInfo: () => subscriptionManager.getSubscriptionInfo(),
    healthCheck: () => subscriptionManager.healthCheck(),
    cleanupAll: () => subscriptionManager.cleanupAllChannels(),
    getActiveChannels: () => subscriptionManager.getActiveChannels()
  }
  
  console.log('Development debug tools loaded, access via window.__debugSupabase')
}

export { subscriptionManager }

// Database type definitions
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

// Extended session interface with related data
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


// Real-time transcription data types
export interface TranscriptEvent {
  index: number
  speaker: string
  timestamp: string
  text: string
  is_final: boolean
}

// AI service response types

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

// Template-related types
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

// API client class
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
    
    // Ensure URL is relative path, force through Next.js proxy
    const finalUrl = url.startsWith('/') ? url : `/${url}`
    
    // API request debugging
    console.log('API request:', {
      method: options.method || 'GET',
      endpoint,
      hasToken: !!token
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
    
    // API response debugging
    console.log('API response:', {
      status: response.status,
      ok: response.ok
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      console.error('API error:', error)
      throw new Error(error.error?.message || `HTTP ${response.status}`)
    }

    return response.json()
  }

  // Session management
  async createSession(title: string, language: string = 'zh-CN', sttModel: string = 'whisper'): Promise<SessionCreateResponse> {
    const response = await this.request<LocalSessionCreateResponse>('/sessions', {
      method: 'POST',
      body: JSON.stringify({
        title,
        language,
        stt_model: sttModel
      })
    })
    
    // Check response format and adapt
    if (isSyncResponse(response)) {
      // New unified response format
      return response as SessionCreateResponse
    } else {
      // Compatible with old format, wrap into new format
      return {
        success: true,
        message: "Session created successfully",
        timestamp: new Date().toISOString(),
        data: response as SessionData
      }
    }
  }

  async finalizeSession(sessionId: string): Promise<SessionFinalizeResponse> {
    // Use V2 API - handle sync response directly
    const baseURL = this.baseURL.replace('/v1', '') // Remove v1, access v2 directly
    
    const response = await fetch(`${baseURL}/v2/sessions/${sessionId}/finalize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.getAuthToken()}`
      }
    })

    if (!response.ok) {
      throw new Error(`Session finalization failed: ${response.status}`)
    }

    const data = await response.json()
    console.log('V2 session finalized:', data)

    // Check if it's an async task response
    if (data.task_id && data.status === "started") {
      // Async task, need to poll
      const result = await this.pollV2TaskStatus(data.task_id)
      return {
        message: "Session finalized successfully.",
        session_id: sessionId,
        status: "completed",
        final_data: result
      }
    } else {
      // Sync response, return directly
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
    
    // Check if it's an async response
    if (this.isAsyncResponse(data)) {
      console.log('Async response detected, starting polling:', data.task_id)
      const result = await this.pollV2TaskStatus(data.task_id)
      const summaryResult = result as { summary: string; key_points?: string[]; metadata?: Record<string, unknown> }
      return {
        summary: summaryResult.summary,
        key_points: summaryResult.key_points || [],
        metadata: summaryResult.metadata || {}
      }
    } else {
      // Return sync response directly
      console.log('Sync response received')
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
        console.log(`V2 task status polling ${attempt + 1}/${maxAttempts}:`, taskStatusResponse.status)

        // Use new type guards and utility functions
        const status = getTaskStatus(taskStatusResponse)
        
        // Task completed
        if (status.isCompleted && taskStatusResponse.result) {
          console.log('V2 task completed, returning result')
          return taskStatusResponse.result
        }

        // Task failed
        if (status.isFailed) {
          console.error('V2 task failed:', taskStatusResponse.error)
          throw new Error(taskStatusResponse.error || 'Task execution failed')
        }

        // Task cancelled
        if (status.isCancelled) {
          console.warn('V2 task cancelled')
          throw new Error('Task cancelled')
        }

        // Task still in progress
        if (status.isPending) {
          console.log('V2 task in progress:', taskStatusResponse.progress)
          await new Promise(resolve => setTimeout(resolve, 3000))
          continue
        }
        
        console.warn('Unknown task status:', taskStatusResponse.status)
        
      } catch (error) {
        console.error(`V2 task status query failed (attempt ${attempt + 1}):`, error)
        
        // If it's an auth error, retry immediately instead of waiting too long
        if (error instanceof Error && error.message.includes('403')) {
          console.warn('Auth error detected, quick retry...')
          if (attempt >= 5) { // Auth errors only retry 5 times
            throw new Error(`Authentication failed, please login again: ${error.message}`)
          }
          await new Promise(resolve => setTimeout(resolve, 1000)) // Brief wait for auth errors
          continue
        }
        
        // Other error handling: throw error on last few attempts
        if (attempt >= maxAttempts - 3) {
          throw error
        }
        
        // Wait before retry
        await new Promise(resolve => setTimeout(resolve, 3000))
      }
    }

    throw new Error(`V2 task polling timeout (${maxAttempts} attempts)`)
  }

  async generateSessionSummary(sessionId: string, _force: boolean = false, templateId?: string): Promise<{ summary: string; metadata: Record<string, unknown> }> {
    try {
      const baseURL = this.baseURL.replace('/v1', '') // Remove v1, access v2 directly
      const token = this.getAuthToken()
      
      if (!token) {
        throw new Error('User not authenticated, unable to generate AI summary')
      }
      
      // Submit V2 async task directly, no need to get session first (avoid additional API calls and auth issues)
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

      if (!taskResponse.ok) {
        const errorData = await taskResponse.json().catch(() => ({}))
        console.error('Failed to submit AI summary task:', errorData)
        throw new Error(`Failed to submit AI summary task: ${taskResponse.status} - ${errorData.detail || taskResponse.statusText}`)
      }

      const taskData = await taskResponse.json()
      console.log('V2 AI summary task submitted:', taskData.task_id)

      // Poll task status
      const result = await this.pollV2TaskStatus(taskData.task_id)
      console.log('V2 AI summary generation completed')
      
      const summaryResult = result as { summary: string }
      return {
        summary: summaryResult.summary,
        metadata: { generated_by: 'v2_async_task' }
      }
    } catch (error) {
      console.error('V2 AI summary generation failed:', error)
      throw error
    }
  }

  async generateTitle(sessionId: string, transcription: string, summary?: string): Promise<AITitleResponse> {
    // Call session-based generate-title API
    const baseURL = this.baseURL.replace('/v1', '') // Remove v1, access v2 directly
    
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

  // Transcription management
  async updateTranscription(transcriptionId: string, segments: unknown[]): Promise<Transcription> {
    return this.request<Transcription>(`/transcriptions/${transcriptionId}`, {
      method: 'PUT',
      body: JSON.stringify({
        segments
      })
    })
  }

  // Template management
  async getTemplates(): Promise<SummaryTemplate[]> {
    const token = this.getAuthToken()
    
    if (!token) {
      throw new Error('User not authenticated, unable to load templates')
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

  // Update session template selection
  async updateSessionTemplate(sessionId: string, templateId: string | null): Promise<{ message: string; session_id: string; template_id: string }> {
    // Convert empty string to null to avoid backend UUID errors
    const finalTemplateId = (!templateId || templateId === '' || templateId === 'no-template') ? null : templateId
    
    return this.request<{ message: string; session_id: string; template_id: string }>(`/sessions/${sessionId}/template`, {
      method: 'PUT',
      body: JSON.stringify({ template_id: finalTemplateId })
    })
  }

  // Retranscribe session
  async retranscribeSession(sessionId: string): Promise<{ success: boolean; message: string; session_id: string; status: string; task_id?: string }> {
    try {
      // Use V2 async API - returns task_id
      const baseURL = this.baseURL.replace('/v1', '') // Remove v1, access v2 directly
      
      const taskResponse = await fetch(`${baseURL}/v2/sessions/${sessionId}/retranscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.getAuthToken()}`
        }
      })

      if (!taskResponse.ok) {
        throw new Error(`Retranscription failed: ${taskResponse.status}`)
      }

      const taskData = await taskResponse.json()
      console.log('V2 retranscription task submitted:', taskData.task_id)

      // Start async polling but return immediately without waiting for completion
      this.pollV2TaskStatus(taskData.task_id).then(result => {
        console.log('V2 retranscription completed:', result)
        
        // After retranscription completes, trigger global event to notify frontend updates
        if (typeof window !== 'undefined') {
          const event = new CustomEvent('retranscriptionCompleted', {
            detail: { sessionId, result }
          })
          window.dispatchEvent(event)
          console.log('Triggered retranscription completed event:', { sessionId, result })
        }
      }).catch(error => {
        console.error('V2 retranscription failed:', error)
      })

      // Return task info immediately
      return {
        success: true,
        message: "Retranscription task submitted, processing in background",
        session_id: sessionId,
        status: "processing",
        task_id: taskData.task_id
      }
      
    } catch (error) {
      console.error('Retranscription API call failed, falling back to V1:', error)
      
      // Fall back to V1 sync API (if V2 unavailable)
      try {
        return await this.request<{ success: boolean; message: string; session_id: string; status: string }>(`/sessions/${sessionId}/retranscribe`, {
          method: 'POST'
        })
      } catch (error) {
        console.warn('V1 retranscribe API also failed:', error)
        return {
          success: false,
          message: "Retranscription feature temporarily unavailable",
          session_id: sessionId,
          status: "failed"
        }
      }
    }
  }
} 