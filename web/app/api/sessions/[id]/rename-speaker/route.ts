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


    // Validate parameters
    if (!oldSpeaker || !newSpeaker) {
      return NextResponse.json(
        { error: 'Missing required parameters: oldSpeaker and newSpeaker' },
        { status: 400 }
      )
    }

    if (oldSpeaker === newSpeaker) {
      return NextResponse.json(
        { error: 'New and old speaker names are the same' },
        { status: 400 }
      )
    }

    // Get authorization header
    const authorization = request.headers.get('authorization')
    if (!authorization || !authorization.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Missing authentication token' },
        { status: 401 }
      )
    }

    // Use unified API client to forward request to backend API
    const token = authorization.replace('Bearer ', '')
    httpClient.setAuthTokenGetter(() => token)
    
    const result = await httpClient.apiServer(`/v1/sessions/${sessionId}/rename-speaker`, {
      method: 'POST',
      body: JSON.stringify({
        oldSpeaker,
        newSpeaker
      })
    })

    return NextResponse.json(result)

  } catch (error) {
    console.error('❌ API Error:', error)
    return NextResponse.json(
      { error: `Internal server error: ${error instanceof Error ? error.message : 'Unknown error'}` },
      { status: 500 }
    )
  }
} 