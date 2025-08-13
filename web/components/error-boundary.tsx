'use client'

import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    
    // 在开发环境中显示更多信息
    if (process.env.NODE_ENV === 'development') {
      console.error('Component stack:', errorInfo.componentStack)
      console.error('Error details:', {
        message: error.message,
        stack: error.stack,
        name: error.name
      })
    }
    
    // 清理可能的订阅或状态
    try {
      // 如果是订阅相关错误，尝试清理全局状态
      if (error.message.includes('subscribe') || 
          error.message.includes('channel') || 
          error.message.includes('supabase') ||
          error.message.includes('realtime')) {
        console.log('🔧 检测到Supabase相关错误，尝试清理状态')
        
        // 清理可能存在的Supabase订阅
        if (typeof window !== 'undefined' && (window as { __subscriptionManager?: { cleanupAllChannels?: () => void } }).__subscriptionManager) {
          console.log('🧹 通过全局订阅管理器清理所有订阅')
          const subscriptionManager = (window as { __subscriptionManager?: { cleanupAllChannels?: () => void } }).__subscriptionManager
          subscriptionManager?.cleanupAllChannels?.()
        }
        
        // 如果存在全局Supabase实例，尝试重置连接
        if (typeof window !== 'undefined' && (window as { __supabase?: unknown }).__supabase) {
          console.log('🔄 尝试重置Supabase实时连接')
          try {
            // 强制断开所有实时连接
            const supabaseInstance = (window as { __supabase?: { realtime?: { disconnect?: () => void } } }).__supabase
            if (supabaseInstance?.realtime && supabaseInstance.realtime.disconnect) {
              supabaseInstance.realtime.disconnect()
            }
          } catch (resetError) {
            console.error('重置Supabase连接失败:', resetError)
          }
        }
      }
      
      // 如果是认证相关错误
      if (error.message.includes('auth') || error.message.includes('GoTrue')) {
        console.log('🔧 检测到认证相关错误，清理认证状态')
        
        // 清理localStorage中的认证数据
        try {
          if (typeof window !== 'undefined') {
            // 清理Supabase认证相关的localStorage
            Object.keys(localStorage).forEach(key => {
              if (key.includes('supabase') || key.includes('auth') || key.includes('asr-fastrtc')) {
                console.log('🗑️ 清理localStorage key:', key)
                localStorage.removeItem(key)
              }
            })
          }
        } catch (storageError) {
          console.error('清理localStorage失败:', storageError)
        }
      }
      
    } catch (cleanupError) {
      console.error('清理过程中发生错误:', cleanupError)
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-100">
          <div className="text-center space-y-6 max-w-md">
            <div className="flex justify-center">
              <AlertTriangle className="h-16 w-16 text-red-500" />
            </div>
            <div className="space-y-2">
              <h1 className="text-2xl font-bold text-gray-900">出现了一些问题</h1>
              <p className="text-gray-600">
                应用遇到了意外错误。请尝试刷新页面，如果问题持续存在，请联系技术支持。
              </p>
            </div>
            {this.state.error && (
              <details className="text-left bg-gray-50 p-4 rounded-lg">
                <summary className="cursor-pointer text-sm font-medium text-gray-700 mb-2">
                  错误详情
                </summary>
                <pre className="text-xs text-gray-600 overflow-auto">
                  {this.state.error.toString()}
                </pre>
              </details>
            )}
            <div className="flex gap-3 justify-center">
              <Button
                onClick={() => window.location.reload()}
                variant="default"
                className="flex items-center gap-2"
              >
                <RefreshCw className="h-4 w-4" />
                刷新页面
              </Button>
              <Button
                onClick={() => this.setState({ hasError: false, error: undefined })}
                variant="outline"
              >
                重试
              </Button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
} 