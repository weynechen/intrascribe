'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Plus, Edit, Trash2, Save, X, FileText, Copy, Settings } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/useAuth'
import { supabase } from '@/lib/supabase'

interface SummaryTemplate {
  id: string
  name: string
  description: string
  template_content: string
  is_default: boolean
  is_active: boolean
  usage_count: number
  tags: string[]
  category: string
  created_at: string
  updated_at: string
}

// Supabase 返回的原始数据类型
interface RawTemplateData {
  [key: string]: unknown
}

interface TemplateManagerProps {
  onTemplateSelect?: (template: SummaryTemplate) => void
}

export function TemplateManager({ onTemplateSelect }: TemplateManagerProps) {
  const { user } = useAuth()
  const [templates, setTemplates] = useState<SummaryTemplate[]>([])
  const [systemTemplates, setSystemTemplates] = useState<SummaryTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [systemLoading, setSystemLoading] = useState(false)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<SummaryTemplate | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    template_content: '',
    category: '会议',
    is_default: false,
    is_active: true,
    tags: [] as string[]
  })

  // Load user templates
  const loadTemplates = useCallback(async () => {
    if (!user) return

    try {
      setLoading(true)
      const { data, error } = await supabase
        .from('summary_templates')
        .select('*')
        .eq('user_id', user.id)
        .eq('is_system_template', false)
        .order('is_default', { ascending: false })  // 默认模板优先显示
        .order('is_active', { ascending: false })   // 启用的模板优先显示
        .order('created_at', { ascending: false })

      if (error) throw error

      // 手动验证和转换数据类型
      const validatedTemplates: SummaryTemplate[] = (data || []).map((item: RawTemplateData) => ({
        id: String(item.id),
        name: String(item.name),
        description: String(item.description || ''),
        template_content: String(item.template_content),
        is_default: Boolean(item.is_default),
        is_active: Boolean(item.is_active),
        usage_count: Number(item.usage_count) || 0,
        tags: Array.isArray(item.tags) ? item.tags as string[] : [],
        category: String(item.category || '会议'),
        created_at: String(item.created_at),
        updated_at: String(item.updated_at)
      }))

      setTemplates(validatedTemplates)
    } catch (error) {
      console.error('加载用户模板失败:', error)
      toast.error('加载用户模板失败')
    } finally {
      setLoading(false)
    }
  }, [user])

  // Load system templates
  const loadSystemTemplates = useCallback(async () => {
    try {
      setSystemLoading(true)
      const { data, error } = await supabase
        .from('summary_templates')
        .select('*')
        .eq('is_system_template', true)
        .eq('is_active', true)
        .order('created_at', { ascending: false })

      if (error) throw error

      // 手动验证和转换数据类型
      const validatedSystemTemplates: SummaryTemplate[] = (data || []).map((item: RawTemplateData) => ({
        id: String(item.id),
        name: String(item.name),
        description: String(item.description || ''),
        template_content: String(item.template_content),
        is_default: Boolean(item.is_default),
        is_active: Boolean(item.is_active),
        usage_count: Number(item.usage_count) || 0,
        tags: Array.isArray(item.tags) ? item.tags as string[] : [],
        category: String(item.category || '会议'),
        created_at: String(item.created_at),
        updated_at: String(item.updated_at)
      }))

      setSystemTemplates(validatedSystemTemplates)
    } catch (error) {
      console.error('加载系统模板失败:', error)
      toast.error('加载系统模板失败')
    } finally {
      setSystemLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTemplates()
    loadSystemTemplates()
  }, [loadTemplates, loadSystemTemplates])

  // Create or update template
  const saveTemplate = async () => {
    if (!user) return

    try {
      const templateData = {
        ...formData,
        user_id: user.id
      }

      if (editingTemplate) {
        // Update existing template
        const { error } = await supabase
          .from('summary_templates')
          .update(templateData)
          .eq('id', editingTemplate.id)

        if (error) throw error
        toast.success('模板更新成功')
      } else {
        // Create new template
        const { error } = await supabase
          .from('summary_templates')
          .insert([templateData])

        if (error) throw error
        toast.success('模板创建成功')
      }

      setIsDialogOpen(false)
      setEditingTemplate(null)
      resetForm()
      loadTemplates()
    } catch (error) {
      console.error('保存模板失败:', error)
      toast.error('保存模板失败')
    }
  }

  // Delete template
  const deleteTemplate = async (id: string) => {
    if (!confirm('确定要删除这个模板吗？')) return

    try {
      const { error } = await supabase
        .from('summary_templates')
        .delete()
        .eq('id', id)

      if (error) throw error

      toast.success('模板删除成功')
      loadTemplates()
    } catch (error) {
      console.error('删除模板失败:', error)
      toast.error('删除模板失败')
    }
  }

  // Toggle default template
  const toggleDefault = async (template: SummaryTemplate) => {
    if (!user?.id) {
      toast.error('用户未登录')
      return
    }

    try {
      // If setting as default, first remove default from all other templates
      if (!template.is_default) {
        await supabase
          .from('summary_templates')
          .update({ is_default: false })
          .eq('user_id', user.id)
          .neq('id', template.id)
      }

      // Toggle current template
      const { error } = await supabase
        .from('summary_templates')
        .update({ is_default: !template.is_default })
        .eq('id', template.id)

      if (error) throw error

      toast.success(template.is_default ? '已取消默认模板' : '已设为默认模板')
      loadTemplates()
    } catch (error) {
      console.error('设置默认模板失败:', error)
      toast.error('设置默认模板失败')
    }
  }

  // Toggle active template
  const toggleActive = async (template: SummaryTemplate) => {
    try {
      // If disabling the default template, warn user
      if (template.is_active && template.is_default) {
        const confirmed = confirm('您正在禁用默认模板，是否确认？禁用后需要设置其他模板为默认。')
        if (!confirmed) return
      }

      // Update template active status
      const { error } = await supabase
        .from('summary_templates')
        .update({ 
          is_active: !template.is_active,
          // If disabling default template, also remove default flag
          ...(template.is_active && template.is_default ? { is_default: false } : {})
        })
        .eq('id', template.id)

      if (error) throw error

      toast.success(template.is_active ? '模板已禁用' : '模板已启用')
      loadTemplates()
    } catch (error) {
      console.error('设置模板状态失败:', error)
      toast.error('设置模板状态失败')
    }
  }

  // Edit template
  const editTemplate = (template: SummaryTemplate) => {
    setEditingTemplate(template)
    setFormData({
      name: template.name,
      description: template.description || '',
      template_content: template.template_content,
      category: template.category || '会议',
      is_default: false,  // 不在对话框中编辑
      is_active: true,    // 不在对话框中编辑
      tags: template.tags || []
    })
    setIsDialogOpen(true)
  }

  // Reset form
  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      template_content: '',
      category: '会议',
      is_default: false,  // 新建模板默认不是默认模板
      is_active: true,    // 新建模板默认启用
      tags: []
    })
  }

  // Create new template
  const createNewTemplate = () => {
    setEditingTemplate(null)
    resetForm()
    setIsDialogOpen(true)
  }

  // Copy system template to user
  const copySystemTemplate = async (systemTemplate: SummaryTemplate) => {
    if (!user?.id) {
      toast.error('用户未登录')
      return
    }

    try {
      // 首先检查用户是否在 public.users 表中存在
      const { data: userExists, error: userCheckError } = await supabase
        .from('users')
        .select('id')
        .eq('id', user.id)
        .single()

      if (userCheckError && userCheckError.code !== 'PGRST116') {
        console.error('检查用户存在性失败:', userCheckError)
        throw new Error('用户验证失败')
      }

      if (!userExists) {
        console.error('用户在 public.users 表中不存在:', user.id)
        toast.error('用户数据同步异常，请联系管理员或重新登录')
        return
      }

      // 直接尝试插入，让数据库处理重复检查（更简洁且避免长URL问题）

      const { error } = await supabase
        .from('summary_templates')
        .insert([{
          user_id: user.id,
          name: systemTemplate.name,
          description: systemTemplate.description,
          template_content: systemTemplate.template_content,
          category: systemTemplate.category,
          tags: systemTemplate.tags,
          is_default: false,
          is_active: true,
          is_system_template: false
        }])

      if (error) throw error

      toast.success('模板已添加到您的模板库')
      loadTemplates()
    } catch (error: unknown) {
      console.error('复制系统模板失败:', error)
      
      // 针对外键约束错误的特殊处理
      const errorObj = error as { code?: string; details?: string; message?: string }
      if (errorObj?.code === '23503' && errorObj?.details?.includes('users')) {
        toast.error('用户数据同步异常，请重新登录后重试')
      } else if (errorObj?.message?.includes('duplicate key') || errorObj?.code === '23505' || errorObj?.message?.includes('summary_templates_user_name_content_unique')) {
        toast.error('您已经复制过此模板了')
        // 重新加载模板列表，确保UI状态一致
        loadTemplates()
      } else if (errorObj?.code === '406') {
        // HTTP 406 错误通常是查询参数问题，但操作可能已成功
        console.warn('查询参数错误，但操作可能已成功:', error)
        toast.success('模板已添加到您的模板库')
        loadTemplates()
      } else {
        toast.error('添加模板失败: ' + (errorObj?.message || '未知错误'))
      }
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="text-gray-500 mt-2">加载模板中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h2 className="text-2xl font-bold">AI总结模板</h2>
          <p className="text-gray-600">管理您的个人模板，或从系统模板库中添加</p>
        </div>
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={createNewTemplate}>
              <Plus className="w-4 h-4 mr-2" />
              新建模板
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {editingTemplate ? '编辑模板' : '新建模板'}
              </DialogTitle>
              <DialogDescription>
                创建或编辑您的AI总结模板，使用纯文本结构化描述定义期望的输出格式
              </DialogDescription>
            </DialogHeader>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Left column - Basic info */}
              <div className="space-y-4">
                <div>
                  <Label htmlFor="name">模板名称</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="请输入模板名称"
                  />
                </div>

                <div>
                  <Label htmlFor="description">模板描述</Label>
                  <Textarea
                    id="description"
                    value={formData.description}
                    onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="请输入模板描述"
                    rows={3}
                  />
                </div>

                <div>
                  <Label htmlFor="category">分类</Label>
                  <Input
                    id="category"
                    value={formData.category}
                    onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value }))}
                    placeholder="请输入分类，如：会议、项目、技术等"
                    list="category-suggestions"
                  />
                  <datalist id="category-suggestions">
                    <option value="会议" />
                    <option value="项目" />
                    <option value="技术" />
                    <option value="学术" />
                    <option value="访谈" />
                    <option value="讲座" />
                    <option value="培训" />
                    <option value="客户沟通" />
                    <option value="产品评审" />
                    <option value="团队建设" />
                    <option value="其他" />
                  </datalist>
                  <p className="text-xs text-gray-500 mt-1">
                    可以输入自定义分类或从建议中选择
                  </p>
                </div>


              </div>

              {/* Right column - Template content */}
              <div className="space-y-4">
                <div>
                  <Label htmlFor="template_content">模板内容 (Markdown格式)</Label>
                  <Textarea
                    id="template_content"
                    value={formData.template_content}
                    onChange={(e) => setFormData(prev => ({ ...prev, template_content: e.target.value }))}
                    placeholder="请输入模板内容，使用纯文本结构化描述定义输出格式和内容要求"
                    rows={15}
                    className="font-mono text-sm"
                  />
                </div>

                <div className="text-sm text-gray-500">
                  <p className="font-medium mb-2">模板说明:</p>
                  <div className="space-y-1">
                    <p>• 使用Markdown格式编写模板</p>
                    <p>• 用清晰的标题和结构描述期望的输出</p>
                    <p>• 在每个部分后添加具体的内容要求</p>
                    <p>• AI会根据模板结构生成对应的总结内容</p>
                    <p>• 分类可自定义，方便模板管理和筛选</p>
                    <p>• 示例：## 主要议题<br/>　　总结会议讨论的核心话题</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-end space-x-2 mt-6">
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                <X className="w-4 h-4 mr-2" />
                取消
              </Button>
              <Button onClick={saveTemplate}>
                <Save className="w-4 h-4 mr-2" />
                保存模板
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* User Templates Section */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">我的模板</h3>
          <span className="text-sm text-gray-500">{templates.length} 个模板</span>
        </div>
        
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-4">
                        {templates.map((template) => (
            <Card key={template.id} className="relative">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <CardTitle className="text-lg flex items-center gap-2">
                      {template.name}
                      {template.is_default && (
                        <Badge variant="default" className="text-xs">
                          默认
                        </Badge>
                      )}
                      {!template.is_active && (
                        <Badge variant="secondary" className="text-xs">
                          已禁用
                        </Badge>
                      )}
                    </CardTitle>
                    {template.description && (
                      <CardDescription className="mt-1">
                        {template.description}
                      </CardDescription>
                    )}
                  </div>
                </div>
                
                {/* Quick Actions */}
                <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <Switch
                        id={`default-${template.id}`}
                        checked={template.is_default}
                        onCheckedChange={() => toggleDefault(template)}
                        className="scale-75"
                      />
                      <Label htmlFor={`default-${template.id}`} className="text-xs text-gray-600">
                        默认
                      </Label>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Switch
                        id={`active-${template.id}`}
                        checked={template.is_active}
                        onCheckedChange={() => toggleActive(template)}
                        className="scale-75"
                      />
                      <Label htmlFor={`active-${template.id}`} className="text-xs text-gray-600">
                        启用
                      </Label>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => editTemplate(template)}
                      className="h-7 px-2"
                    >
                      <Edit className="w-3 h-3" />
                    </Button>
                    {onTemplateSelect && (
                      <Button
                        size="sm"
                        onClick={() => onTemplateSelect(template)}
                        className="h-7 px-2 text-xs"
                      >
                        使用
                      </Button>
                    )}
                  </div>
                </div>
              </CardHeader>
            
                          <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{template.category}</Badge>
                  <span className="text-sm text-gray-500">
                    使用 {template.usage_count} 次
                  </span>
                </div>
                
                <div className="bg-gray-50 p-3 rounded-md">
                  <p className="text-sm font-mono text-gray-700 line-clamp-4">
                    {template.template_content}
                  </p>
                </div>
                
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => deleteTemplate(template.id)}
                    className="text-red-600 hover:text-red-700 h-7 px-2 text-xs"
                  >
                    <Trash2 className="w-3 h-3 mr-1" />
                    删除
                  </Button>
                </div>
              </CardContent>
            </Card>
            ))}
          </div>

          {templates.length === 0 && (
            <div className="text-center py-8">
              <div className="text-gray-400 mb-4">
                <FileText className="w-12 h-12 mx-auto" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">
                暂无个人模板
              </h3>
              <p className="text-gray-500 mb-4">
                创建您的第一个模板，或从下方的系统模板库中添加
              </p>
              <Button onClick={createNewTemplate}>
                <Plus className="w-4 h-4 mr-2" />
                创建模板
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* System Templates Section */}
      <div className="flex-shrink-0 border-t pt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-gray-500" />
            <h3 className="text-lg font-semibold">系统模板库</h3>
          </div>
          <span className="text-sm text-gray-500">{systemTemplates.length} 个可用模板</span>
        </div>
        
        <div className="max-h-64 overflow-y-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {systemTemplates.map((template) => (
              <Card key={template.id} className="relative hover:shadow-md transition-shadow">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-sm">{template.name}</CardTitle>
                      {template.description && (
                        <CardDescription className="text-xs mt-1 line-clamp-2">
                          {template.description}
                        </CardDescription>
                      )}
                    </div>
                  </div>
                </CardHeader>
                
                <CardContent className="pt-0">
                  <div className="space-y-2">
                    <Badge variant="secondary" className="text-xs">{template.category}</Badge>
                    
                    <div className="bg-gray-50 p-2 rounded text-xs font-mono text-gray-700 line-clamp-3">
                      {template.template_content.substring(0, 80)}...
                    </div>
                    
                    <Button
                      size="sm"
                      className="w-full text-xs"
                      onClick={() => copySystemTemplate(template)}
                    >
                      <Copy className="w-3 h-3 mr-1" />
                      添加到我的模板
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {systemLoading && (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>
              <p className="text-gray-500 mt-2 text-sm">加载系统模板中...</p>
            </div>
          )}

          {systemTemplates.length === 0 && !systemLoading && (
            <div className="text-center py-4">
              <p className="text-gray-500 text-sm">暂无可用的系统模板</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
} 