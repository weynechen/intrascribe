/**
 * 统一API响应格式类型定义
 * 匹配后端 response_schemas.py 的定义
 */

// =============== 基础响应类型 ===============

export interface BaseResponse {
  success: boolean
  message: string
  timestamp: string
}

// =============== 同步接口响应格式 ===============

export interface SyncResponse<T = any> extends BaseResponse {
  data: T
}

export interface SyncListResponse<T = any> extends BaseResponse {
  data: T[]
  total?: number
  page?: number
  size?: number
}

// =============== 异步接口响应格式 ===============

export interface AsyncResponse extends BaseResponse {
  task_id: string
  status: string
  poll_url: string
  estimated_duration?: number
}

// =============== 任务状态响应格式 ===============

export interface TaskStatusResponse extends BaseResponse {
  task_id: string
  status: 'pending' | 'started' | 'success' | 'failure' | 'cancelled'
  progress?: {
    current?: number
    total?: number
    description?: string
    [key: string]: any
  }
  result?: {
    [key: string]: any
  }
  error?: string
  created_at?: string
  started_at?: string
  completed_at?: string
}

// 任务状态便利属性
export interface TaskStatus {
  isPending: boolean
  isCompleted: boolean
  isFailed: boolean
  isCancelled: boolean
}

// =============== 错误响应格式 ===============

export interface ErrorResponse extends BaseResponse {
  success: false
  error_code?: string
  error_type?: string
  details?: {
    [key: string]: any
  }
}

// =============== 业务相关响应类型 ===============

// 会话相关
export interface SessionData {
  session_id: string
  title: string
  status: string
  created_at: string
  language: string
  usage_hint?: string
}

export interface SessionCreateResponse extends SyncResponse<SessionData> {}

export interface SessionUpdateResponse extends SyncResponse<SessionData> {}

export interface SessionDeleteResponse extends SyncResponse<{
  session_id: string
  deleted: boolean
}> {}

// 会话异步操作响应
export interface AsyncSessionResponse extends AsyncResponse {
  // 继承基础异步响应，可添加会话特定字段
}

// AI服务相关
export interface AISummaryData {
  summary: string
  key_points: string[]
  metadata: {
    model_used?: string
    processing_time?: number
    template_used?: string
    [key: string]: any
  }
}

export interface AsyncAIResponse extends AsyncResponse {
  // 继承基础异步响应，可添加AI特定字段
}

// 转录相关
export interface TranscriptionData {
  transcription_id: string
  session_id: string
  content: string
  segments: TranscriptionSegment[]
  word_count: number
  language: string
}

export interface TranscriptionSegment {
  index: number
  speaker: string
  start_time: number
  end_time: number
  text: string
  confidence_score: number
  is_final: boolean
}

export interface AsyncTranscriptionResponse extends AsyncResponse {
  // 继承基础异步响应，可添加转录特定字段
}

// 批量转录响应
export interface BatchTranscriptionData {
  session_id: string
  audio_file_id: string
  transcription_id: string
  original_filename: string
  statistics: {
    total_segments: number
    total_duration_seconds: number
    speaker_count: number
    transcription_length: number
  }
  transcription: {
    content: string
    segments: TranscriptionSegment[]
  }
}

// =============== 响应格式检测类型守卫 ===============

export function isAsyncResponse(response: any): response is AsyncResponse {
  return response && 
         typeof response === 'object' && 
         'task_id' in response && 
         'poll_url' in response
}

export function isSyncResponse(response: any): response is SyncResponse {
  return response && 
         typeof response === 'object' && 
         'data' in response && 
         !('task_id' in response)
}

export function isErrorResponse(response: any): response is ErrorResponse {
  return response && 
         typeof response === 'object' && 
         response.success === false
}

export function isTaskStatusResponse(response: any): response is TaskStatusResponse {
  return response && 
         typeof response === 'object' && 
         'task_id' in response && 
         'status' in response && 
         !('poll_url' in response)
}

// =============== 任务状态工具函数 ===============

export function getTaskStatus(response: TaskStatusResponse): TaskStatus {
  return {
    isPending: response.status === 'pending' || response.status === 'started',
    isCompleted: response.status === 'success',
    isFailed: response.status === 'failure', 
    isCancelled: response.status === 'cancelled'
  }
}

// =============== 兼容性类型 (向后兼容) ===============

// 保持与现有代码的兼容性
export interface SessionFinalizeResponse {
  message: string
  session_id: string
  status: string
  final_data: any
}

export interface AISummaryResponse {
  summary: string
  key_points?: string[]
  metadata: {
    model_used?: string
    success?: boolean
    total_processing_time?: number
    transcription_length?: number
    timestamp?: number
    error?: string
    fallback_used?: boolean
    [key: string]: any
  }
}

// =============== API方法返回类型 ===============

export type CreateSessionResult = Promise<SessionCreateResponse>
export type UpdateSessionResult = Promise<SessionUpdateResponse>  
export type DeleteSessionResult = Promise<SessionDeleteResponse>
export type FinalizeSessionResult = Promise<SessionFinalizeResponse>
export type GenerateSummaryResult = Promise<AISummaryResponse>
export type BatchTranscriptionResult = Promise<AsyncTranscriptionResponse>
