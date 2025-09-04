'use client'

import { useEffect, useState } from 'react'
import { Badge } from './ui/badge'
import { Progress } from './ui/progress'
import { toast } from 'sonner'
import { TaskStatusResponse, getTaskStatus } from '@/lib/api-types'

// Task result type
interface TaskResult {
  [key: string]: unknown
}
import { supabase } from '@/lib/supabase'

interface TaskStatusDisplayProps {
  taskId: string
  onComplete?: (result: TaskResult) => void
  onError?: (error: string) => void
  onCancel?: () => void
  showProgress?: boolean
  autoHide?: boolean
  className?: string
}

export function TaskStatusDisplay({
  taskId,
  onComplete,
  onError,
  onCancel,
  showProgress = true,
  autoHide = false,
  className
}: TaskStatusDisplayProps) {
  const [taskStatus, setTaskStatus] = useState<TaskStatusResponse | null>(null)
  const [progress, setProgress] = useState(0)
  const [hidden, setHidden] = useState(false)
  
  // 获取认证token
  const getAuthToken = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return session?.access_token || null
  }
  
  // 轮询任务状态
  useEffect(() => {
    if (!taskId) return
    
    let intervalId: NodeJS.Timeout | null = null
    
    const pollTaskStatus = async () => {
      try {
        const token = await getAuthToken()
        if (!token) {
          throw new Error('未找到认证令牌')
        }
        
        const response = await fetch(`/api/v2/tasks/${taskId}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        
        const status: TaskStatusResponse = await response.json()
        setTaskStatus(status)
        
        const taskInfo = getTaskStatus(status)
        
        // 更新进度
        if (status.progress) {
          const progressPercent = status.progress.current && status.progress.total
            ? (status.progress.current / status.progress.total) * 100
            : progress < 90 ? progress + 10 : 90 // 简单的进度模拟
          setProgress(progressPercent)
        }
        
        // 处理任务完成
        if (taskInfo.isCompleted) {
          if (intervalId) clearInterval(intervalId)
          setProgress(100)
          
          if (status.result && onComplete) {
            onComplete(status.result)
          }
          
          if (autoHide) {
            setTimeout(() => setHidden(true), 2000)
          }
        }
        
        // 处理任务失败
        if (taskInfo.isFailed) {
          if (intervalId) clearInterval(intervalId)
          
          const error = status.error || '任务执行失败'
          toast.error(error)
          
          if (onError) {
            onError(error)
          }
        }
        
        // 处理任务取消
        if (taskInfo.isCancelled) {
          if (intervalId) clearInterval(intervalId)
          
          toast.info('任务已取消')
          
          if (onCancel) {
            onCancel()
          }
        }
        
      } catch (error) {
        console.error('轮询任务状态失败:', error)
        if (intervalId) clearInterval(intervalId)
        
        const errorMsg = error instanceof Error ? error.message : '获取任务状态失败'
        toast.error(errorMsg)
        
        if (onError) {
          onError(errorMsg)
        }
      }
    }
    
    // 立即执行一次
    pollTaskStatus()
    
    // 设置轮询间隔
    intervalId = setInterval(pollTaskStatus, 2000)
    
    return () => {
      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  }, [taskId, onComplete, onError, onCancel, autoHide, progress])
  
  // 取消任务
  const handleCancel = async () => {
    try {
      const token = await getAuthToken()
      if (!token) return
      
      const response = await fetch(`/api/v2/tasks/${taskId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (response.ok) {
        toast.info('任务取消请求已提交')
      }
    } catch (error) {
      console.error('取消任务失败:', error)
      toast.error('取消任务失败')
    }
  }
  
  if (hidden) return null
  
  if (!taskStatus) {
    return (
      <div className={`flex items-center space-x-2 ${className}`}>
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm text-gray-600">初始化任务...</span>
      </div>
    )
  }
  
  const status = getTaskStatus(taskStatus)
  
  // 状态徽章颜色映射
  const getStatusBadge = () => {
    if (status.isPending) {
      return <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">进行中</Badge>
    }
    if (status.isCompleted) {
      return <Badge variant="secondary" className="bg-green-100 text-green-800">已完成</Badge>
    }
    if (status.isFailed) {
      return <Badge variant="destructive">失败</Badge>
    }
    if (status.isCancelled) {
      return <Badge variant="secondary" className="bg-gray-100 text-gray-800">已取消</Badge>
    }
    return <Badge variant="outline">{taskStatus.status}</Badge>
  }
  
  return (
    <div className={`p-4 bg-white border rounded-lg shadow-sm ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium">任务状态</span>
          {getStatusBadge()}
        </div>
        
        {status.isPending && (
          <button
            onClick={handleCancel}
            className="text-xs text-red-600 hover:text-red-800 underline"
          >
            取消
          </button>
        )}
      </div>
      
      {showProgress && status.isPending && (
        <div className="mb-2">
          <Progress value={progress} className="w-full h-2" />
          <div className="flex justify-between mt-1">
            <span className="text-xs text-gray-500">
              {taskStatus.progress?.description || '处理中...'}
            </span>
            <span className="text-xs text-gray-500">{Math.round(progress)}%</span>
          </div>
        </div>
      )}
      
      {taskStatus.message && (
        <p className="text-sm text-gray-600 mt-2">{taskStatus.message}</p>
      )}
      
      {status.isFailed && taskStatus.error && (
        <p className="text-sm text-red-600 mt-2 p-2 bg-red-50 rounded">
          错误: {taskStatus.error}
        </p>
      )}
      
      <div className="flex justify-between items-center mt-2 text-xs text-gray-400">
        <span>任务ID: {taskId.slice(-8)}</span>
        {taskStatus.created_at && (
          <span>创建时间: {new Date(taskStatus.created_at).toLocaleTimeString()}</span>
        )}
      </div>
    </div>
  )
}
