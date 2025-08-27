'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Mic, Calendar, Clock, X, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DirectLiveKitRecorder } from '@/components/direct-livekit-recorder'
import '@livekit/components-styles'
import { TranscriptEvent, supabase } from '@/lib/supabase'
import { useAuth } from '@/hooks/useAuth'
import { toast } from 'sonner'

interface Recording {
  id: string
  timestamp: string
  duration: string
  transcript: string
  aiSummary?: string
  aiTitle?: string
  status?: string
  templateId?: string
}

// 简化的模板类型，只包含查询返回的字段
interface SummaryTemplate {
  id: string
  name: string
  description: string | null
  template_content: string
  is_default: boolean
  is_active: boolean
  category: string
}

// Supabase 返回的原始数据类型
interface RawTemplateData {
  id: unknown
  name: unknown
  description: unknown
  template_content: unknown
  is_default: unknown
  is_active: unknown
  category: unknown
}

interface FileListProps {
  recordings: Recording[]
  selectedId?: string
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
  onTranscript?: (transcriptEvent: TranscriptEvent) => void
  onRecordingStateChange?: (isRecording: boolean) => void
  onSessionCreated?: (sessionId: string) => void
  onTemplateSelect?: (sessionId: string, templateId: string) => void
  isRecording?: boolean
}

export function FileList({ 
  recordings, 
  selectedId, 
  onSelect, 
  onDelete,
  onTranscript, 
  onRecordingStateChange,
  onSessionCreated,
  onTemplateSelect,
  isRecording = false 
}: FileListProps) {
  const { user } = useAuth()
  const [showRecorder, setShowRecorder] = useState(false)
  const [templates, setTemplates] = useState<SummaryTemplate[]>([])
  // const [templatesLoading, setTemplatesLoading] = useState(false)

  // 添加调试信息
  useEffect(() => {
    console.log('📂 FileList组件收到数据:', {
      recordingsCount: recordings.length,
      selectedId,
      isRecording,
      recordingsPreview: recordings.slice(0, 3).map(r => ({
        id: r.id,
        title: r.aiTitle || `录音 ${r.id.slice(-8)}`,
        status: r.status,
        timestamp: r.timestamp,
        templateId: r.templateId
      }))
    })
  }, [recordings, selectedId, isRecording])

  // 加载模板列表
  const loadTemplates = useCallback(async () => {
    if (!user) return

    try {
      // setTemplatesLoading(true)
      const { data, error } = await supabase
        .from('summary_templates')
        .select('id, name, description, template_content, is_default, is_active, category')
        .eq('user_id', user.id)
        .eq('is_active', true)
        .order('is_default', { ascending: false })
        .order('name', { ascending: true })

      if (error) throw error

      // 手动验证和转换数据类型
      const validatedTemplates: SummaryTemplate[] = (data || []).map((item: RawTemplateData) => ({
        id: String(item.id),
        name: String(item.name),
        description: item.description ? String(item.description) : null,
        template_content: String(item.template_content),
        is_default: Boolean(item.is_default),
        is_active: Boolean(item.is_active),
        category: String(item.category)
      }))

      setTemplates(validatedTemplates)
    } catch (error) {
      console.error('加载模板失败:', error)
      toast.error('加载模板失败')
    } finally {
      // setTemplatesLoading(false)
    }
  }, [user])

  useEffect(() => {
    loadTemplates()
  }, [loadTemplates])

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diffInHours = Math.abs(now.getTime() - date.getTime()) / (1000 * 60 * 60)
    
    if (diffInHours < 24) {
      return date.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
      })
    } else {
      return date.toLocaleDateString('zh-CN', { 
        month: 'short', 
        day: 'numeric' 
      })
    }
  }

  const handleDeleteClick = (e: React.MouseEvent, recordingId: string) => {
    e.stopPropagation()
    onDelete?.(recordingId)
  }

  const handleRecordingStateChange = (recording: boolean) => {
    if (!recording) {
      setShowRecorder(false)
    }
    onRecordingStateChange?.(recording)
  }

  const startNewRecording = () => {
    setShowRecorder(true)
  }

  // 处理模板选择
  const handleTemplateChange = (sessionId: string, templateId: string) => {
    // 将"default"转换为空字符串传递给后端
    const finalTemplateId = templateId === 'default' ? '' : templateId
    console.log('🔧 FileList模板选择:', { sessionId, templateId, finalTemplateId })
    onTemplateSelect?.(sessionId, finalTemplateId)
  }

  // 获取模板名称
  const getTemplateName = (templateId?: string) => {
    if (!templateId || templateId === 'default') return '默认模板'
    const template = templates.find(t => t.id === templateId)
    return template?.name || '未知模板'
  }

  return (
    <div className="w-80 h-full bg-white border-r border-gray-200 flex flex-col">
      {/* Header */}
      <div className="h-16 border-b border-gray-200 px-4 flex items-center justify-between flex-shrink-0">
        <h2 className="font-semibold text-gray-900">文件列表</h2>
        <Button
          onClick={startNewRecording}
          disabled={isRecording}
          size="sm"
          className="bg-red-500 hover:bg-red-600 text-white"
        >
          <Mic className="h-4 w-4 mr-1" />
          新建录音
        </Button>
      </div>

      {/* Recorder Component - 只在需要时显示 */}
      {showRecorder && (
        <div className="p-4 border-b border-gray-200 bg-gray-50">
          <div className="text-center">
            <DirectLiveKitRecorder
              onTranscript={onTranscript || (() => {})}
              onRecordingStateChange={handleRecordingStateChange}
              onSessionCreated={onSessionCreated}
            />
          </div>
        </div>
      )}

      {/* Recording Status */}
      {isRecording && (
        <div className="px-4 py-3 bg-red-50 border-b border-red-200 flex items-center">
          <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse mr-2"></div>
          <span className="text-sm text-red-700 font-medium">录音中...</span>
        </div>
      )}

      {/* File List */}
      <div className="flex-1 overflow-y-auto">
        {recordings.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Mic className="h-12 w-12 mb-4 text-gray-300" />
            <p className="text-sm">暂无录音文件</p>
            <p className="text-xs mt-1">点击&quot;新建录音&quot;开始录制</p>
          </div>
        ) : (
          <div className="p-2 space-y-2">
            {recordings.map((recording) => (
              <Card
                key={recording.id}
                className={cn(
                  "p-3 cursor-pointer hover:bg-gray-50 transition-colors relative group",
                  selectedId === recording.id && "bg-blue-50 border-blue-200"
                )}
                onClick={() => onSelect(recording.id)}
              >
                {/* Delete Button */}
                {onDelete && (
                  <button
                    onClick={(e) => handleDeleteClick(e, recording.id)}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-200 rounded"
                    title="删除录音"
                  >
                    <X className="h-3 w-3 text-gray-500" />
                  </button>
                )}

                {/* Title */}
                <div className="font-medium text-sm text-gray-900 mb-1 pr-6">
                  {recording.aiTitle || `录音 ${recording.id.slice(-8)}`}
                </div>

                {/* Metadata */}
                <div className="flex items-center text-xs text-gray-500 space-x-3 mb-2">
                  <div className="flex items-center">
                    <Calendar className="h-3 w-3 mr-1" />
                    {formatDate(recording.timestamp)}
                  </div>
                  <div className="flex items-center">
                    <Clock className="h-3 w-3 mr-1" />
                    {recording.duration}
                  </div>
                </div>

                {/* Status and Template Selection */}
                <div className="flex items-center mb-2 space-x-2">
                  {/* Status Badge */}
                  {recording.status && (
                    <div className={cn(
                      "text-xs px-2 py-1 rounded-full flex-shrink-0",
                      recording.status === 'completed' && "bg-green-100 text-green-700",
                      recording.status === 'recording' && "bg-red-100 text-red-700",
                      recording.status === 'created' && "bg-yellow-100 text-yellow-700",
                      recording.status === 'failed' && "bg-red-100 text-red-700"
                    )}>
                      {recording.status === 'completed' && '已完成'}
                      {recording.status === 'recording' && '录音中'}
                      {recording.status === 'created' && '已创建'}
                      {recording.status === 'failed' && '失败'}
                    </div>
                  )}

                  {/* Template Selection */}
                  {recording.status === 'completed' && templates.length > 0 && (
                    <div className="flex-shrink-0">
                      <Select
                        value={recording.templateId || 'default'}
                        onValueChange={(templateId) => handleTemplateChange(recording.id, templateId)}
                      >
                        <SelectTrigger 
                          className="h-6 text-xs border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 px-2 w-auto"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center space-x-1">
                            <FileText className="h-3 w-3 flex-shrink-0" />
                            <SelectValue 
                              placeholder="选择模板"
                            >
                              <span>{getTemplateName(recording.templateId)}</span>
                            </SelectValue>
                          </div>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="default">默认模板</SelectItem>
                          {templates.map((template) => (
                            <SelectItem key={template.id} value={template.id}>
                              <div className="flex items-center space-x-2">
                                <span>{template.name}</span>
                                {template.is_default && (
                                  <span className="text-xs text-blue-600">(默认)</span>
                                )}
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>

                {/* Preview */}
                {recording.aiSummary ? (
                  <p className="text-xs text-gray-600 line-clamp-2">
                    {recording.aiSummary}
                  </p>
                ) : recording.transcript ? (
                  <p className="text-xs text-gray-600 line-clamp-2">
                    {recording.transcript}
                  </p>
                ) : (
                  <p className="text-xs text-gray-400 italic">暂无内容</p>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
} 