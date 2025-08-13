import { NextRequest, NextResponse } from 'next/server'

// 后端服务的基础URL
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const resolvedParams = await params
  try {
    const sessionId = resolvedParams.id
    const body = await request.json()
    const { oldSpeaker, newSpeaker } = body

    console.log('📥 收到说话人重命名请求:', { sessionId, oldSpeaker, newSpeaker })

    // 验证参数
    if (!oldSpeaker || !newSpeaker) {
      return NextResponse.json(
        { error: '缺少必要参数: oldSpeaker 和 newSpeaker' },
        { status: 400 }
      )
    }

    if (oldSpeaker === newSpeaker) {
      return NextResponse.json(
        { error: '新旧说话人名称相同' },
        { status: 400 }
      )
    }

    // 获取认证头
    const authorization = request.headers.get('authorization')
    if (!authorization || !authorization.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: '缺少认证令牌' },
        { status: 401 }
      )
    }

    // 转发请求到后端API
    const backendUrl = `${BACKEND_URL}/api/v1/sessions/${sessionId}/rename-speaker`
    console.log('🔄 调用后端API:', backendUrl)
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authorization,
      },
      body: JSON.stringify({
        oldSpeaker,
        newSpeaker
      })
    })

    console.log('📡 后端API响应状态:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.log('❌ 后端API调用失败:', errorText)
      
      let errorData
      try {
        errorData = JSON.parse(errorText)
      } catch {
        errorData = { error: errorText }
      }
      
      return NextResponse.json(
        { error: errorData.detail || errorData.error || '说话人重命名失败' },
        { status: response.status }
      )
    }

    const result = await response.json()
    console.log('✅ 说话人重命名成功')

    return NextResponse.json(result)

  } catch (error) {
    console.error('❌ API Error:', error)
    return NextResponse.json(
      { error: `服务器内部错误: ${error instanceof Error ? error.message : '未知错误'}` },
      { status: 500 }
    )
  }
} 