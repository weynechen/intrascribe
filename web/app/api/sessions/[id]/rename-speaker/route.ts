import { NextRequest, NextResponse } from 'next/server'
import { httpClient } from '@/lib/api-client'

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

    // 使用统一API客户端转发请求到后端API
    const token = authorization.replace('Bearer ', '')
    httpClient.setAuthTokenGetter(() => token)
    console.log('🔄 调用后端API:', `/v1/sessions/${sessionId}/rename-speaker`)
    
    const result = await httpClient.apiServer(`/v1/sessions/${sessionId}/rename-speaker`, {
      method: 'POST',
      body: JSON.stringify({
        oldSpeaker,
        newSpeaker
      })
    })
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