import { NextRequest, NextResponse } from 'next/server'

// 标题生成功能已集成到V2会话处理流程中
// 此端点现在仅提供基于内容的智能标题生成

function generateSmartTitle(transcription: string, summary?: string): string {
  try {
    // 使用总结内容（如果有）或转录内容的前50个字符生成标题
    const content = summary || transcription
    
    if (!content || content.length < 10) {
      return `会议记录 ${new Date().toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })}`
    }

    // 提取关键词生成标题
    const keywords = content
      .replace(/[^\u4e00-\u9fa5\w\s]/g, ' ') // 保留中文、英文和数字
      .split(/\s+/)
      .filter(word => word.length > 1)
      .slice(0, 8) // 取前8个词

    if (keywords.length > 0) {
      const title = keywords.slice(0, 4).join(' ')
      return title.length > 20 ? title.substring(0, 20) + '...' : title
    }

    // 如果没有找到关键词，使用时间戳标题
    return `会议记录 ${new Date().toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })}`

  } catch (error) {
    console.error('生成智能标题失败:', error)
    return `会议记录 ${new Date().toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })}`
  }
}

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

    console.log('🔄 生成智能标题...')
    const title = generateSmartTitle(transcription, summary)
    console.log('✅ 标题生成成功:', title)

    return NextResponse.json({
      title,
      metadata: {
        generated_by: 'local_algorithm',
        fallback_used: false,
        timestamp: Date.now()
      }
    })

  } catch (error) {
    console.error('标题生成失败:', error)
    
    // 返回回退标题
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
      }
    )
  }
} 