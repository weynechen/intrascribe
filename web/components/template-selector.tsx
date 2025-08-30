'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { FileText, Star, Eye } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/useAuth'
import { SummaryTemplate, APIClient } from '@/lib/supabase'

interface TemplateSelectorProps {
  selectedTemplateId?: string
  onTemplateChange: (templateId: string | undefined) => void
  onGenerateSummary: (templateId?: string) => void
  isLoading?: boolean
}

export function TemplateSelector({ 
  selectedTemplateId, 
  onTemplateChange, 
  onGenerateSummary,
  isLoading = false 
}: TemplateSelectorProps) {
  const { session } = useAuth()
  const [templates, setTemplates] = useState<SummaryTemplate[]>([])
  const [loading, setLoading] = useState(true)
  // const [previewTemplate, setPreviewTemplate] = useState<SummaryTemplate | null>(null)
  const [apiClient, setApiClient] = useState<APIClient | null>(null)

  // 初始化API客户端
  useEffect(() => {
    console.log('🔑 Template-selector认证状态:', {
      hasSession: !!session,
      hasAccessToken: !!session?.access_token,
      tokenPreview: session?.access_token ? `${session.access_token.substring(0, 20)}...` : null
    })
    
    if (session?.access_token) {
      const client = new APIClient('/api/v1', () => session.access_token)
      setApiClient(client)
    } else {
      console.warn('⚠️ 无法创建API客户端：缺少认证token')
      setApiClient(null)
    }
  }, [session?.access_token])

  // 加载模板
  const loadTemplates = useCallback(async () => {
    if (!apiClient) {
      console.warn('⚠️ API客户端未初始化，跳过模板加载')
      return
    }
    
    if (!session?.access_token) {
      console.warn('⚠️ 用户未认证，跳过模板加载')
      return
    }

    try {
      setLoading(true)
      console.log('🔄 开始加载模板...')
      const templatesData = await apiClient.getTemplates()
      
      // 过滤掉默认模板，只显示用户自定义模板
      const userTemplates = templatesData.filter(template => !template.is_default)
      setTemplates(userTemplates)
      
      console.log('✅ 模板加载成功:', {
        total: templatesData.length,
        userTemplates: userTemplates.length,
        defaultTemplatesFiltered: templatesData.length - userTemplates.length
      })
      
      // 如果没有选中模板且有用户模板，不自动选择任何模板
      // 用户需要主动选择或使用"不使用模板"选项
    } catch (error) {
      console.error('加载模板失败:', error)
      toast.error('加载模板失败')
    } finally {
      setLoading(false)
    }
  }, [apiClient, selectedTemplateId, onTemplateChange, session?.access_token])

  useEffect(() => {
    loadTemplates()
  }, [loadTemplates])

  const handleGenerateClick = () => {
    console.log('🔍 模板选择器调试:', {
      selectedTemplateId,
      selectedTemplateIdType: typeof selectedTemplateId,
      isString: typeof selectedTemplateId === 'string'
    })
    onGenerateSummary(selectedTemplateId)
  }

  const selectedTemplate = templates.find(t => t.id === selectedTemplateId)

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700">总结模板</span>
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">总结模板</span>
        <div className="flex items-center space-x-2">
          {selectedTemplate && (
            <Dialog>
              <DialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"

                >
                  <Eye className="w-4 h-4 mr-1" />
                  预览
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <FileText className="w-5 h-5" />
                    {selectedTemplate.name}
                    {selectedTemplate.is_default && (
                      <Badge variant="default" className="text-xs">
                        <Star className="w-3 h-3 mr-1" />
                        默认
                      </Badge>
                    )}
                  </DialogTitle>
                  <DialogDescription>
                    {selectedTemplate.description || '无描述'}
                  </DialogDescription>
                </DialogHeader>
                
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{selectedTemplate.category}</Badge>
                    <span className="text-sm text-gray-500">
                      使用 {selectedTemplate.usage_count} 次
                    </span>
                  </div>
                  
                  <div>
                    <h4 className="text-sm font-medium mb-2">模板内容:</h4>
                    <div className="bg-gray-50 p-4 rounded-md">
                      <pre className="text-sm whitespace-pre-wrap font-mono">
                        {selectedTemplate.template_content}
                      </pre>
                    </div>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      <div className="flex space-x-2">
        <Select
          value={selectedTemplateId || 'no-template'}
          onValueChange={(value) => onTemplateChange(value === 'no-template' ? undefined : value)}
        >
          <SelectTrigger className="flex-1">
            <SelectValue placeholder="选择总结模板" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="no-template">不使用模板</SelectItem>
            {templates.map((template) => (
              <SelectItem key={template.id} value={template.id}>
                <div className="flex items-center gap-2">
                  <span>{template.name}</span>
                  {template.is_default && (
                    <Star className="w-3 h-3 text-yellow-500 fill-current" />
                  )}
                  <Badge variant="outline" className="text-xs">
                    {template.category}
                  </Badge>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button onClick={handleGenerateClick} disabled={isLoading}>
          {isLoading ? (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
          ) : (
            '生成总结'
          )}
        </Button>
      </div>

      {selectedTemplate && (
        <div className="text-xs text-gray-500 bg-gray-50 p-2 rounded-md">
          <strong>{selectedTemplate.name}</strong>: {selectedTemplate.description || '无描述'}
        </div>
      )}

      {templates.length === 0 && (
        <div className="text-center py-4 text-gray-500 text-sm">
          <FileText className="w-8 h-8 mx-auto mb-2 text-gray-400" />
          <p>暂无可用模板</p>
          <p className="text-xs">请前往&quot;我的模板&quot;页面创建模板</p>
        </div>
      )}
    </div>
  )
} 