import { NextRequest, NextResponse } from 'next/server'

// 后端服务的基础URL
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

// Task status interface
interface TaskResult {
  summary: string
  key_points: string[]
  summary_id?: string
}

// 轮询任务状态的辅助函数
async function pollTaskStatus(taskId: string, maxAttempts: number = 120): Promise<TaskResult> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const statusResponse = await fetch(`${BACKEND_URL}/api/v2/tasks/${taskId}`)
    
    if (!statusResponse.ok) {
      throw new Error(`获取任务状态失败: ${statusResponse.status}`)
    }
    
    const status = await statusResponse.json()
    console.log(`📊 任务状态检查 (${attempt + 1}/${maxAttempts}):`, status.status)
    
    if (status.ready) {
      if (status.successful) {
        return status.result
      } else {
        throw new Error(status.error || '任务执行失败')
      }
    }
    
    // 等待3秒后继续轮询
    await new Promise(resolve => setTimeout(resolve, 3000))
  }
  
  throw new Error('任务处理超时')
}

export async function POST(request: NextRequest) {
  try {
    console.log('📥 收到AI总结请求')
    const { transcription, sessionId, templateId } = await request.json()
    console.log('📝 转录内容长度:', transcription?.length || 0)

    if (!transcription || !sessionId) {
      console.log('❌ 缺少必要参数')
      return NextResponse.json(
        { error: '缺少转录内容或会话ID' },
        { status: 400 }
      )
    }

    console.log('🔄 提交V2异步AI总结任务...')
    // 调用V2 API提交异步任务
    const taskResponse = await fetch(`${BACKEND_URL}/api/v2/sessions/${sessionId}/ai-summary`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // 这里需要添加认证头，实际使用时从request中获取
        // 'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ 
        transcription_text: transcription,
        template_id: templateId || null
      })
    })

    console.log('📡 后端任务提交响应状态:', taskResponse.status)

    if (!taskResponse.ok) {
      const errorText = await taskResponse.text()
      console.log('❌ 任务提交失败:', errorText)
      throw new Error(`任务提交失败: ${taskResponse.status} ${taskResponse.statusText}`)
    }

    const taskData = await taskResponse.json()
    const taskId = taskData.task_id
    console.log('✅ 异步任务已提交，任务ID:', taskId)

    // 轮询任务状态直到完成
    console.log('⏳ 开始轮询任务状态...')
    const result = await pollTaskStatus(taskId)
    console.log('✅ AI总结生成完成')

    // 返回总结结果
    return NextResponse.json({
      summary: result.summary,
      key_points: result.key_points,
      summary_id: result.summary_id
    })

  } catch (error) {
    console.error('总结生成失败:', error)
    
    return NextResponse.json(
      { error: `总结生成失败: ${error instanceof Error ? error.message : '未知错误'}` },
      { status: 500 }
    )
  }
} 