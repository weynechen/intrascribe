import { NextRequest, NextResponse } from 'next/server'

// Title generation functionality has been integrated into V2 session processing flow
// This endpoint now only provides content-based smart title generation

function generateSmartTitle(transcription: string, summary?: string): string {
  try {
    // Use summary content (if available) or first 50 characters of transcription to generate title
    const content = summary || transcription
    
    if (!content || content.length < 10) {
      return `Meeting Record ${new Date().toLocaleString('en-US', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })}`
    }

    // Extract keywords to generate title
    const keywords = content
      .replace(/[^\u4e00-\u9fa5\w\s]/g, ' ') // Keep Chinese, English and numbers
      .split(/\s+/)
      .filter(word => word.length > 1)
      .slice(0, 8) // Take first 8 words

    if (keywords.length > 0) {
      const title = keywords.slice(0, 4).join(' ')
      return title.length > 20 ? title.substring(0, 20) + '...' : title
    }

    // If no keywords found, use timestamp title
    return `Meeting Record ${new Date().toLocaleString('en-US', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })}`

  } catch (error) {
    return `Meeting Record ${new Date().toLocaleString('en-US', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })}`
  }
}

export async function POST(request: NextRequest) {
  try {
    const { transcription, summary } = await request.json()

    if (!transcription) {
      return NextResponse.json(
        { error: 'Missing text content' },
        { status: 400 }
      )
    }

    const title = generateSmartTitle(transcription, summary)

    return NextResponse.json({
      title,
      metadata: {
        generated_by: 'local_algorithm',
        fallback_used: false,
        timestamp: Date.now()
      }
    })

  } catch (error) {
    
    // Return fallback title
    const fallbackTitle = `Meeting Record ${new Date().toLocaleString('en-US', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })}`
    
    
    return NextResponse.json(
      { 
        title: fallbackTitle,
        metadata: {
          error: error instanceof Error ? error.message : 'Unknown error',
          fallback_used: true,
          timestamp: Date.now()
        }
      }
    )
  }
} 