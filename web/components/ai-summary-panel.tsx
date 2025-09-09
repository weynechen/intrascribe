'use client'

import React, { useState, useEffect } from 'react'
import { MessageSquare, Copy, X, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { apiPut, httpClient } from '@/lib/api-client'
import { toast } from 'sonner'
import MDEditor from '@uiw/react-md-editor'
import '@uiw/react-md-editor/markdown-editor.css'
import { TemplateSelector } from './template-selector'

interface AISummaryPanelProps {
  isVisible: boolean
  onClose: () => void
  sessionId?: string
  transcription?: string
  summary?: string
  title?: string
  isLoading: boolean
  onSummaryUpdate?: (summary: string) => void
  onTitleUpdate?: (title: string) => void
  summaryId?: string
  transcriptionId?: string
  onRefreshSessions?: () => void
  onGenerateSummary?: (templateId?: string) => void
}

export function AISummaryPanel({ 
  isVisible, 
  onClose, 
  sessionId,
  transcription,
  summary, 
  isLoading,
  onSummaryUpdate,
  summaryId,
  transcriptionId,
  onRefreshSessions,
  onGenerateSummary
}: AISummaryPanelProps) {
  const [markdownContent, setMarkdownContent] = useState<string>('')
  const [isSaving, setIsSaving] = useState(false)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | undefined>()

  const { session } = useAuth()

  // 当summary变化时，直接显示原始内容
  useEffect(() => {
    console.log('🔄 AI总结面板: summary变化:', {
      hasSummary: !!summary,
      summaryLength: summary?.length || 0,
      summaryPreview: summary?.substring(0, 100) || ''
    })
    if (summary) {
      setMarkdownContent(summary)
    }
  }, [summary])

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success('内容已复制到剪贴板')
    }).catch(err => {
      console.error('Failed to copy content: ', err)
      toast.error('复制失败')
    })
  }

  const handleSave = async () => {
    if (!sessionId) {
      toast.error('缺少会话信息')
      return
    }

    if (!summaryId) {
      toast.error('请先生成AI总结后再进行编辑保存')
      return
    }

    if (!session?.access_token) {
      toast.error('用户未登录')
      return
    }

    try {
      setIsSaving(true)
      console.log('💾 开始保存AI总结内容:', markdownContent)
      
      // 验证内容不为空
      if (!markdownContent || markdownContent.trim().length === 0) {
        toast.error('内容不能为空')
        console.error('❌ 用户输入的内容为空:', { markdownContent })
        return
      }

      // 调用更新API - 直接保存用户输入的完整内容
      const requestBody = {
        session_id: sessionId,
        transcription_id: transcriptionId || null,
        summary: markdownContent, // 直接保存用户编辑的完整内容
        key_points: [],
        action_items: [],
        ai_model: 'user_edited',
        ai_provider: 'manual'
      }
      
      console.log('📤 发送请求到API:', requestBody)

      // 使用统一API客户端更新AI总结
      httpClient.setAuthTokenGetter(() => session.access_token)
      const result = await apiPut('api', `/v2/sessions/${sessionId}/ai-summaries/${summaryId}`, requestBody)
      console.log('✅ 保存成功:', result)
      
      // 通知父组件更新
      if (onSummaryUpdate) {
        onSummaryUpdate(markdownContent) // 传递完整内容
      }
      
      toast.success('内容已保存到数据库')
      
      // 刷新会话数据以确保数据一致性
      if (onRefreshSessions) {
        console.log('🔄 保存后刷新会话数据以确保一致性')
        onRefreshSessions()
      }
    } catch (error) {
      console.error('❌ 保存失败:', error)
      toast.error(`保存失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsSaving(false)
    }
  }

  if (!isVisible) return null

  return (
    <div className="flex-1 bg-white border-l border-gray-200 flex flex-col">
      <div className="h-10 border-b border-gray-200 px-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center space-x-2">
          <MessageSquare className="h-4 w-4 text-blue-600" />
          <h2 className="font-medium text-gray-900 text-sm">AI 总结</h2>
        </div>
        <div className="flex items-center space-x-1">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-7 w-7"
            onClick={() => copyToClipboard(markdownContent)}
            title="复制内容"
          >
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-7 w-7"
            onClick={handleSave}
            title={!summaryId ? "请先生成AI总结" : "保存"}
            disabled={isSaving || !summaryId}
          >
            {isSaving ? (
              <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-gray-900"></div>
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-7 w-7"
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="flex space-x-1">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="ml-3 text-sm text-gray-500">
              AI 正在处理...
            </span>
          </div>
        ) : !transcription ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-500">
              <MessageSquare className="h-12 w-12 mx-auto mb-4 text-gray-300" />
              <p className="text-sm">开始录音后，转录内容会显示在这里</p>
              <p className="text-xs mt-2 text-gray-400">然后您可以生成AI总结</p>
            </div>
          </div>
        ) : !summary && !isLoading ? (
          <div className="p-4 space-y-4">
            <div className="text-center">
              <MessageSquare className="h-12 w-12 mx-auto mb-4 text-gray-300" />
              <p className="text-sm text-gray-600 mb-4">选择模板生成AI总结</p>
            </div>
            <TemplateSelector
              selectedTemplateId={selectedTemplateId}
              onTemplateChange={setSelectedTemplateId}
              onGenerateSummary={onGenerateSummary || (() => {})}
              isLoading={isLoading}
            />
          </div>
        ) : (
          <div className="h-full flex flex-col">
            <MDEditor
              value={markdownContent}
              onChange={(val) => setMarkdownContent(val || '')}
              preview="preview"
              hideToolbar={false}
              visibleDragbar={false}
              textareaProps={{
                placeholder: 'AI生成的总结内容将显示在这里，您可以编辑和完善...',
                style: {
                  fontSize: 14,
                  lineHeight: 1.6,
                }
              }}
              data-color-mode="light"
              height="calc(100% - 30px)"
            />
            <div className="px-1 py-0.5 text-xs text-gray-500 bg-gray-50 border-t">
              <p>💡 编辑提示：您可以自由编辑总结内容，编辑完成后请点击保存按钮。</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
} 