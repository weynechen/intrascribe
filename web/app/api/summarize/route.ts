import { NextRequest, NextResponse } from 'next/server'
import { httpClient } from '@/lib/api-client'

// Task status interface
interface TaskResult {
  summary: string
  key_points: string[]
  summary_id?: string
}

interface TaskStatus {
  ready: boolean
  successful?: boolean
  result?: TaskResult
  error?: string
}

interface TaskData {
  task_id: string
}

// Helper function to poll task status
async function pollTaskStatus(taskId: string, maxAttempts: number = 120): Promise<TaskResult> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    // Use unified API client to query task status
    const status = await httpClient.apiServer(`/v2/tasks/${taskId}`, {
      method: 'GET',
      skipAuth: true // API route to API route, no auth needed
    }) as TaskStatus
    
    if (status.ready) {
      if (status.successful && status.result) {
        return status.result
      } else {
        throw new Error(status.error || 'Task execution failed')
      }
    }
    
    // Wait 3 seconds before continuing polling
    await new Promise(resolve => setTimeout(resolve, 3000))
  }
  
  throw new Error('Task processing timeout')
}

export async function POST(request: NextRequest) {
  try {
    const { transcription, sessionId, templateId } = await request.json()

    if (!transcription || !sessionId) {
      return NextResponse.json(
        { error: 'Missing transcription content or session ID' },
        { status: 400 }
      )
    }

    // Use unified API client to submit async task
    const taskData = await httpClient.apiServer(`/v2/sessions/${sessionId}/ai-summary`, {
      method: 'POST',
      body: JSON.stringify({ 
        transcription_text: transcription,
        template_id: templateId || null
      }),
      skipAuth: true // API route inter-calls, skip auth temporarily
    }) as TaskData
    const taskId = taskData.task_id

    // Poll task status until completion
    const result = await pollTaskStatus(taskId)

    // Return summary result
    return NextResponse.json({
      summary: result.summary,
      key_points: result.key_points,
      summary_id: result.summary_id
    })

  } catch (error) {
    
    return NextResponse.json(
      { error: `Summary generation failed: ${error instanceof Error ? error.message : 'Unknown error'}` },
      { status: 500 }
    )
  }
} 