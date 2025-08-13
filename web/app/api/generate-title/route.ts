import { NextRequest, NextResponse } from 'next/server'

// 后端服务的基础URL
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    console.log('📥 收到生成标题请求')
    const { transcription, summary } = await request.json()
    console.log('📝 转录内容长度:', transcription?.length || 0)
    console.log('📄 总结内容长度:', summary?.length || 0)

    if (!transcription) {
      console.log('❌ 缺少转录内容')
      return NextResponse.json(
        { error: '缺少文本内容' },
        { status: 400 }
      )
    }

    console.log('🔄 调用后端API生成标题...')
    // 调用后端的真实API接口
    const response = await fetch(`${BACKEND_URL}/api/generate-title`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        transcription,
        summary: summary || null
      }), // 使用transcription字段，summary是可选的
    })

    console.log('📡 后端API响应状态:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.log('❌ 后端API调用失败:', errorText)
      throw new Error(`后端API调用失败: ${response.status} ${response.statusText}`)
    }

    const data = await response.json()
    console.log('✅ 标题生成成功:', data.title)

    // 返回与后端一致的响应格式
    return NextResponse.json(data)

  } catch (error) {
    console.error('标题生成失败:', error)
    
    // 如果后端不可用，返回回退标题
    const fallbackTitle = `会议记录 ${new Date().toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })}`
    
    console.log('🔄 使用回退标题:', fallbackTitle)
    
    return NextResponse.json(
      { 
        title: fallbackTitle,
        metadata: {
          error: error instanceof Error ? error.message : '未知错误',
          fallback_used: true,
          timestamp: Date.now()
        }
      },
      { status: 500 }
    )
  }
} 