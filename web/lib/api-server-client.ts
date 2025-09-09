/**
 * API Server client - unified handling of all API Server calls
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
 * API Server client class
 */
export class APIServerClient {
  constructor() {
    // Authentication token will be set dynamically before use
  }
  
  setAuthToken(token: string | null) {
    httpClient.setAuthTokenGetter(() => token)
  }

  // =============== Session Management ===============
  
  async createSession(title: string, language: string = 'zh-CN', sttModel: string = 'whisper'): Promise<SessionCreateResponse> {
    const response = await httpClient.post<LocalSessionCreateResponse>('api', '/v1/sessions', {
      title,
      language,
      stt_model: sttModel
    })
    
    // Check response format and adapt
    if (isSyncResponse(response)) {
      return response as SessionCreateResponse
    } else {
      return {
        success: true,
        message: "Session created successfully",
        timestamp: new Date().toISOString(),
        data: response as SessionData
      }
    }
  }

  async finalizeSession(sessionId: string): Promise<SessionFinalizeResponse> {
    const response = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/finalize`)

    if (response.task_id && response.status === "started") {
      const result = await this.pollV2TaskStatus(response.task_id)
      return {
        message: "Session finalized successfully.",
        session_id: sessionId,
        status: "completed",
        final_data: result
      }
    } else {
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
    
    if (isSyncResponse(response)) {
      return response
    } else {
      return {
        success: true,
        message: "Session deleted successfully",
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

  // =============== AI Services ===============

  async generateSummary(transcription: string, sessionId: string, templateId?: string): Promise<AISummaryResponse> {
    const response = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/summarize`, {
      transcription_text: transcription,
      ...(templateId && { template_id: templateId })
    })
    
    if (this.isAsyncResponse(response)) {
      const result = await this.pollV2TaskStatus(response.task_id)
      const summaryResult = result as { summary: string; key_points?: string[]; metadata?: Record<string, unknown> }
      return {
        summary: summaryResult.summary,
        key_points: summaryResult.key_points || [],
        metadata: summaryResult.metadata || {}
      }
    } else {
      return {
        summary: response.summary,
        key_points: response.key_points || [],
        metadata: response.metadata || {}
      }
    }
  }

  async generateSessionSummary(sessionId: string, _force: boolean = false, templateId?: string): Promise<{ summary: string; metadata: Record<string, unknown> }> {
    try {
      const taskResponse = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/ai-summary`, {
        template_id: templateId || null
      })

      const result = await this.pollV2TaskStatus(taskResponse.task_id)
      
      const summaryResult = result as { summary: string }
      return {
        summary: summaryResult.summary,
        metadata: { generated_by: 'v2_async_task' }
      }
    } catch (error) {
      throw error
    }
  }

  async generateTitle(sessionId: string, transcription: string, summary?: string): Promise<AITitleResponse> {
    return httpClient.post<AITitleResponse>('api', `/v2/sessions/${sessionId}/generate-title`, {
      transcription_text: transcription,
      summary_text: summary
    })
  }

  // =============== Transcription Management ===============

  async updateTranscription(transcriptionId: string, segments: unknown[]) {
    return httpClient.put('api', `/v1/transcriptions/${transcriptionId}`, {
      segments
    })
  }

  // =============== Template Management ===============

  async getTemplates(): Promise<SummaryTemplate[]> {
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

  async updateSessionTemplate(sessionId: string, templateId: string | null): Promise<{ message: string; session_id: string; template_id: string }> {
    // Convert empty string to null to avoid backend UUID errors
    const finalTemplateId = (!templateId || templateId === '' || templateId === 'no-template') ? null : templateId
    
    return httpClient.put<{ message: string; session_id: string; template_id: string }>('api', `/v1/sessions/${sessionId}/template`, {
      template_id: finalTemplateId
    })
  }

  // =============== Retranscription ===============

  async retranscribeSession(sessionId: string): Promise<{ success: boolean; message: string; session_id: string; status: string; task_id?: string }> {
    try {
      const taskResponse = await httpClient.post<any>('api', `/v2/sessions/${sessionId}/retranscribe`)

      // Start async polling, but return immediately without waiting for completion
      this.pollV2TaskStatus(taskResponse.task_id).then(_result => {
        // Polling completed successfully
      }).catch(_error => {
        // Polling failed
      })

      return {
        success: true,
        message: "Retranscription task submitted, processing in background",
        session_id: sessionId,
        status: "processing",
        task_id: taskResponse.task_id
      }
      
    } catch (error) {
      // Fallback to V1 sync API if V2 is unavailable
      try {
        return await httpClient.post<{ success: boolean; message: string; session_id: string; status: string }>('api', `/v1/sessions/${sessionId}/retranscribe`)
      } catch (error) {
        return {
          success: false,
          message: "Retranscription feature temporarily unavailable",
          session_id: sessionId,
          status: "failed"
        }
      }
    }
  }

  // =============== Utility Methods ===============

  // Response format detection and handling
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

  // Helper method for polling V2 task status
  private async pollV2TaskStatus(taskId: string, maxAttempts: number = 120): Promise<unknown> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const taskStatusResponse: TaskStatusResponse = await httpClient.get<TaskStatusResponse>('api', `/v2/tasks/${taskId}`)

        const status = getTaskStatus(taskStatusResponse)
        
        if (status.isCompleted && taskStatusResponse.result) {
          return taskStatusResponse.result
        }

        if (status.isFailed) {
          throw new Error(taskStatusResponse.error || 'Task execution failed')
        }

        if (status.isCancelled) {
          throw new Error('Task was cancelled')
        }

        if (status.isPending) {
          await new Promise(resolve => setTimeout(resolve, 3000))
          continue
        }
        
      } catch (error) {
        if (error instanceof Error && error.message.includes('403')) {
          if (attempt >= 5) {
            throw new Error(`Authentication failed, please login again: ${error.message}`)
          }
          await new Promise(resolve => setTimeout(resolve, 1000))
          continue
        }
        
        if (attempt >= maxAttempts - 3) {
          throw error
        }
        
        await new Promise(resolve => setTimeout(resolve, 3000))
      }
    }

    throw new Error(`V2 task polling timeout (${maxAttempts} attempts)`)
  }
}

// Create and export singleton instance
export const apiServerClient = new APIServerClient()

// Export convenience functions
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
