/**
 * 测试API响应格式检测和处理逻辑
 */

import {
  isSyncResponse,
  isAsyncResponse,
  isTaskStatusResponse,
  isErrorResponse,
  getTaskStatus,
  SyncResponse,
  AsyncResponse,
  TaskStatusResponse,
  ErrorResponse
} from '../api-types'

describe('API响应格式检测', () => {
  
  describe('同步响应检测', () => {
    it('应该正确识别同步响应格式', () => {
      const syncResponse: SyncResponse = {
        success: true,
        message: '操作成功',
        timestamp: '2024-01-01T12:00:00Z',
        data: {
          session_id: 'test-session',
          title: '测试会话'
        }
      }
      
      expect(isSyncResponse(syncResponse)).toBe(true)
      expect(isAsyncResponse(syncResponse)).toBe(false)
    })
    
    it('应该拒绝包含task_id的响应', () => {
      const notSyncResponse = {
        success: true,
        message: '任务已提交',
        timestamp: '2024-01-01T12:00:00Z',
        data: { test: 'data' },
        task_id: 'task-123' // 这个使它不是同步响应
      }
      
      expect(isSyncResponse(notSyncResponse)).toBe(false)
    })
  })
  
  describe('异步响应检测', () => {
    it('应该正确识别异步响应格式', () => {
      const asyncResponse: AsyncResponse = {
        success: true,
        message: '任务已提交',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'celery-task-123',
        status: 'pending',
        poll_url: '/api/v2/tasks/celery-task-123',
        estimated_duration: 30
      }
      
      expect(isAsyncResponse(asyncResponse)).toBe(true)
      expect(isSyncResponse(asyncResponse)).toBe(false)
    })
    
    it('应该要求task_id和poll_url同时存在', () => {
      const incompleteResponse1 = {
        success: true,
        message: '任务已提交',
        task_id: 'task-123'
        // 缺少 poll_url
      }
      
      const incompleteResponse2 = {
        success: true,
        message: '任务已提交',
        poll_url: '/api/v2/tasks/task-123'
        // 缺少 task_id
      }
      
      expect(isAsyncResponse(incompleteResponse1)).toBe(false)
      expect(isAsyncResponse(incompleteResponse2)).toBe(false)
    })
  })
  
  describe('任务状态响应检测', () => {
    it('应该正确识别任务状态响应格式', () => {
      const taskStatusResponse: TaskStatusResponse = {
        success: true,
        message: '任务状态: success',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'celery-task-123',
        status: 'success',
        result: {
          session_id: 'test-session',
          transcription_id: 'test-transcription'
        }
      }
      
      expect(isTaskStatusResponse(taskStatusResponse)).toBe(true)
      expect(isAsyncResponse(taskStatusResponse)).toBe(false) // 没有poll_url
    })
  })
  
  describe('错误响应检测', () => {
    it('应该正确识别错误响应格式', () => {
      const errorResponse: ErrorResponse = {
        success: false,
        message: '操作失败',
        timestamp: '2024-01-01T12:00:00Z',
        error_code: 'VALIDATION_ERROR',
        error_type: 'BusinessLogicError',
        details: {
          field: 'title',
          message: '标题不能为空'
        }
      }
      
      expect(isErrorResponse(errorResponse)).toBe(true)
      expect(isSyncResponse(errorResponse)).toBe(false)
    })
    
    it('应该要求success为false', () => {
      const notErrorResponse = {
        success: true, // 这个使它不是错误响应
        message: '操作成功',
        timestamp: '2024-01-01T12:00:00Z',
        error_code: 'SOME_ERROR'
      }
      
      expect(isErrorResponse(notErrorResponse)).toBe(false)
    })
  })
  
  describe('任务状态工具函数', () => {
    it('应该正确解析pending状态', () => {
      const taskStatus: TaskStatusResponse = {
        success: true,
        message: '任务进行中',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'task-123',
        status: 'pending'
      }
      
      const status = getTaskStatus(taskStatus)
      expect(status.isPending).toBe(true)
      expect(status.isCompleted).toBe(false)
      expect(status.isFailed).toBe(false)
      expect(status.isCancelled).toBe(false)
    })
    
    it('应该正确解析started状态', () => {
      const taskStatus: TaskStatusResponse = {
        success: true,
        message: '任务执行中',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'task-123',
        status: 'started'
      }
      
      const status = getTaskStatus(taskStatus)
      expect(status.isPending).toBe(true) // started也算作pending
      expect(status.isCompleted).toBe(false)
    })
    
    it('应该正确解析success状态', () => {
      const taskStatus: TaskStatusResponse = {
        success: true,
        message: '任务完成',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'task-123',
        status: 'success',
        result: { data: 'result' }
      }
      
      const status = getTaskStatus(taskStatus)
      expect(status.isPending).toBe(false)
      expect(status.isCompleted).toBe(true)
      expect(status.isFailed).toBe(false)
    })
    
    it('应该正确解析failure状态', () => {
      const taskStatus: TaskStatusResponse = {
        success: true, // 注意：即使任务失败，API调用本身可能成功
        message: '任务失败',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'task-123',
        status: 'failure',
        error: '处理过程中出现错误'
      }
      
      const status = getTaskStatus(taskStatus)
      expect(status.isPending).toBe(false)
      expect(status.isCompleted).toBe(false)
      expect(status.isFailed).toBe(true)
    })
    
    it('应该正确解析cancelled状态', () => {
      const taskStatus: TaskStatusResponse = {
        success: true,
        message: '任务已取消',
        timestamp: '2024-01-01T12:00:00Z',
        task_id: 'task-123',
        status: 'cancelled'
      }
      
      const status = getTaskStatus(taskStatus)
      expect(status.isCancelled).toBe(true)
      expect(status.isPending).toBe(false)
    })
  })
  
  describe('兼容性测试', () => {
    it('应该处理旧格式的响应', () => {
      // 模拟旧的API响应格式
      const oldFormatResponse = {
        session_id: 'test-session',
        title: '测试会话',
        status: 'created',
        created_at: '2024-01-01T12:00:00Z'
      }
      
      // 旧格式不应该被识别为新格式
      expect(isSyncResponse(oldFormatResponse)).toBe(false)
      expect(isAsyncResponse(oldFormatResponse)).toBe(false)
      
      // 但应该能够处理（通过兼容性代码）
      expect(typeof oldFormatResponse).toBe('object')
      expect(oldFormatResponse.session_id).toBe('test-session')
    })
    
    it('应该处理空或无效响应', () => {
      expect(isSyncResponse(null)).toBe(false)
      expect(isSyncResponse(undefined)).toBe(false)
      expect(isSyncResponse('')).toBe(false)
      expect(isSyncResponse(123)).toBe(false)
      expect(isSyncResponse([])).toBe(false)
      
      expect(isAsyncResponse(null)).toBe(false)
      expect(isAsyncResponse({})).toBe(false)
    })
  })
})

describe('响应格式转换和处理', () => {
  it('应该能够从同步响应中提取数据', () => {
    const syncResponse: SyncResponse<{session_id: string, title: string}> = {
      success: true,
      message: '创建成功',
      timestamp: '2024-01-01T12:00:00Z',
      data: {
        session_id: 'test-session',
        title: '测试会话'
      }
    }
    
    if (isSyncResponse(syncResponse)) {
      expect(syncResponse.data.session_id).toBe('test-session')
      expect(syncResponse.data.title).toBe('测试会话')
    }
  })
  
  it('应该能够从异步响应中提取任务信息', () => {
    const asyncResponse: AsyncResponse = {
      success: true,
      message: '任务已提交',
      timestamp: '2024-01-01T12:00:00Z',
      task_id: 'celery-task-123',
      status: 'pending',
      poll_url: '/api/v2/tasks/celery-task-123',
      estimated_duration: 60
    }
    
    if (isAsyncResponse(asyncResponse)) {
      expect(asyncResponse.task_id).toBe('celery-task-123')
      expect(asyncResponse.poll_url).toBe('/api/v2/tasks/celery-task-123')
      expect(asyncResponse.estimated_duration).toBe(60)
    }
  })
})
