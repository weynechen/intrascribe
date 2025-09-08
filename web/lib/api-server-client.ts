/**
 * API Server客户端 - 统一处理所有API Server调用
 * 替代原有的APIClient类，支持环境切换无感知
 */

import { httpClient } from './api-client'
import { 
  TaskStatusResponse, SessionData,
  SessionCreateResponse, SessionDeleteResponse, SessionFinalizeResponse,
  AISummaryResponse,
  isSyncResponse,
  getTaskStatus
} from './api-types'

// Template types
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

// AI Service response types
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

// Legacy compatibility interface
interface LocalSessionCreateResponse {
  session_id: string
  title: string
  status: string
  created_at: string
  language: string
  usage_hint: string
}

/**
 * API Server客户端类
 */
export class APIServerClient {
  constructor() {
    // 认证token需要在使用前动态设置
    // 不在构造函数中设置固定的token获取器
  }
  
  // 设置认证token
  setAuthToken(token: string | null) {
    httpClient.setAuthTokenGetter(() => token)
  }

  // =============== 会话管理 ===============
  
  async createSession(title: string, language: string = 'zh-CN', sttModel: string = 'whisper'): Promise<SessionCreateResponse> {
    const response = await httpClient.post<LocalSessionCreateResponse>('api', '/v1/sessions', {
      title,
      language,
      stt_model: sttModel
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
    const response = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/finalize`)

    console.log('✅ V2会话结束完成:', response)

    // 检查是否是异步任务响应
    if (response.task_id && response.status === "started") {
      // 异步任务，需要轮询
      const result = await this.pollV2TaskStatus(response.task_id)
      return {
        message: "Session finalized successfully.",
        session_id: sessionId,
        status: "completed",
        final_data: result
      }
    } else {
      // 同步响应，直接返回
      return {
        message: response.message || "Session finalized successfully.",
        session_id: sessionId,
        status: "completed",
        final_data: response.result || {
          total_duration_seconds: 0,
          transcription_saved: true
        }
      }
    }
  }

  async deleteSession(sessionId: string): Promise<SessionDeleteResponse> {
    const response = await httpClient.delete<SessionDeleteResponse>('api', `/v1/sessions/${sessionId}`)
    
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

  async getSession(sessionId: string) {
    return httpClient.get('api', `/v1/sessions/${sessionId}`)
  }

  // =============== AI服务 ===============

  async generateSummary(transcription: string, sessionId: string, templateId?: string): Promise<AISummaryResponse> {
    // 调用基于session的summarize API
    const response = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/summarize`, {
      transcription_text: transcription,
      ...(templateId && { template_id: templateId })
    })
    
    // 检查是否是异步响应
    if (this.isAsyncResponse(response)) {
      console.log('🔄 检测到异步响应，开始轮询:', response.task_id)
      const result = await this.pollV2TaskStatus(response.task_id)
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
        summary: response.summary,
        key_points: response.key_points || [],
        metadata: response.metadata || {}
      }
    }
  }

  async generateSessionSummary(sessionId: string, force: boolean = false, templateId?: string): Promise<{ summary: string; metadata: Record<string, unknown> }> {
    console.log('🌐 APIServerClient.generateSessionSummary V2调试:', {
      sessionId,
      force,
      templateId,
      templateIdType: typeof templateId,
      isTemplateIdString: typeof templateId === 'string'
    })
    
    try {
      // 直接提交V2异步任务
      const taskResponse = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/ai-summary`, {
        template_id: templateId || null
      })

      console.log('📡 AI总结任务提交响应:', taskResponse)
      console.log('✅ V2 AI总结任务已提交:', taskResponse.task_id)

      // 轮询任务状态
      const result = await this.pollV2TaskStatus(taskResponse.task_id)
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
    return httpClient.post<AITitleResponse>('api', `/v2/sessions/${sessionId}/generate-title`, {
      transcription_text: transcription,
      summary_text: summary
    })
  }

  // =============== 转录管理 ===============

  async updateTranscription(transcriptionId: string, segments: unknown[]) {
    return httpClient.put('api', `/v1/transcriptions/${transcriptionId}`, {
      segments
    })
  }

  // =============== 模板管理 ===============

  async getTemplates(): Promise<SummaryTemplate[]> {
    console.log('🔑 模板加载调试')
    return httpClient.get<SummaryTemplate[]>('api', '/v1/templates/')
  }

  async createTemplate(template: CreateTemplateRequest): Promise<SummaryTemplate> {
    return httpClient.post<SummaryTemplate>('api', '/v1/templates', template)
  }

  async updateTemplate(templateId: string, template: Partial<CreateTemplateRequest>): Promise<SummaryTemplate> {
    return httpClient.put<SummaryTemplate>('api', `/v1/templates/${templateId}`, template)
  }

  async deleteTemplate(templateId: string): Promise<{ message: string; template_id: string }> {
    return httpClient.delete<{ message: string; template_id: string }>('api', `/v1/templates/${templateId}`)
  }

  async getTemplate(templateId: string): Promise<SummaryTemplate> {
    return httpClient.get<SummaryTemplate>('api', `/v1/templates/${templateId}`)
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
    
    return httpClient.put<{ message: string; session_id: string; template_id: string }>('api', `/v1/sessions/${sessionId}/template`, {
      template_id: finalTemplateId
    })
  }

  // =============== 重新转录 ===============

  async retranscribeSession(sessionId: string): Promise<{ success: boolean; message: string; session_id: string; status: string; task_id?: string }> {
    try {
      // 使用V2异步API - 返回task_id
      const taskResponse = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/retranscribe`)

      console.log('✅ V2重新转录任务已提交:', taskResponse.task_id)

      // 启动异步轮询，但不等待完成就返回
      this.pollV2TaskStatus(taskResponse.task_id).then(result => {
        console.log('✅ V2重新转录完成:', result)
      }).catch(error => {
        console.error('❌ V2重新转录失败:', error)
      })

      // 立即返回任务信息
      return {
        success: true,
        message: "重新转录任务已提交，正在后台处理",
        session_id: sessionId,
        status: "processing",
        task_id: taskResponse.task_id
      }
      
    } catch (error) {
      console.error('重新转录API调用失败，回退到V1:', error)
      
      // 回退到V1同步API（如果V2不可用）
      try {
        return await httpClient.post<{ success: boolean; message: string; session_id: string; status: string }>('api', `/v1/sessions/${sessionId}/retranscribe`)
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

  // =============== 工具方法 ===============

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

  // 轮询V2任务状态的辅助方法
  private async pollV2TaskStatus(taskId: string, maxAttempts: number = 120): Promise<unknown> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const taskStatusResponse: TaskStatusResponse = await httpClient.get<TaskStatusResponse>('api', `/v2/tasks/${taskId}`)
        
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
}

// 创建和导出单例实例
export const apiServerClient = new APIServerClient()

// 导出便利函数
export const createSession = (title: string, language?: string, sttModel?: string) =>
  apiServerClient.createSession(title, language, sttModel)

export const finalizeSession = (sessionId: string) =>
  apiServerClient.finalizeSession(sessionId)

export const deleteSession = (sessionId: string) =>
  apiServerClient.deleteSession(sessionId)

export const generateSummary = (transcription: string, sessionId: string, templateId?: string) =>
  apiServerClient.generateSummary(transcription, sessionId, templateId)

export const generateSessionSummary = (sessionId: string, force?: boolean, templateId?: string) =>
  apiServerClient.generateSessionSummary(sessionId, force, templateId)

export const generateTitle = (sessionId: string, transcription: string, summary?: string) =>
  apiServerClient.generateTitle(sessionId, transcription, summary)

export const getTemplates = () =>
  apiServerClient.getTemplates()

export const retranscribeSession = (sessionId: string) =>
  apiServerClient.retranscribeSession(sessionId)
