import { NextRequest, NextResponse } from 'next/server'

// 后端服务的基础URL
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    console.log('📥 收到AI总结请求')
    const { transcription } = await request.json()
    console.log('📝 转录内容长度:', transcription?.length || 0)

    if (!transcription) {
      console.log('❌ 缺少转录内容')
      return NextResponse.json(
        { error: '缺少文本内容' },
        { status: 400 }
      )
    }

    console.log('🔄 调用后端API生成总结...')
    // 调用后端的真实API接口
    const response = await fetch(`${BACKEND_URL}/api/summarize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ transcription }), // 使用transcription字段
    })

    console.log('📡 后端API响应状态:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.log('❌ 后端API调用失败:', errorText)
      throw new Error(`后端API调用失败: ${response.status} ${response.statusText}`)
    }

    const data = await response.json()
    console.log('✅ AI总结生成成功')

    // 返回与后端一致的响应格式
    return NextResponse.json(data)

  } catch (error) {
    console.error('总结生成失败:', error)
    
    // 如果后端不可用，返回错误信息
    return NextResponse.json(
      { error: `总结生成失败: ${error instanceof Error ? error.message : '未知错误'}` },
      { status: 500 }
    )
  }
} 