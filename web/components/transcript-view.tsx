'use client'

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { User, Copy, Edit3, Check, X, RefreshCw, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'

interface TranscriptItem {
  id: string
  timestamp: string
  speaker?: string
  text: string
}

interface TranscriptViewProps {
  transcript: TranscriptItem[]
  timestamp: string
  isRecording: boolean
  onTranscriptUpdate?: (updatedTranscript: TranscriptItem[]) => void
  // Add new props for audio playback sync
  currentPlaybackTime?: number // Current audio playback time in seconds
  onSeekToTime?: (timeInSeconds: number) => void // Callback to seek audio to specific time
  // Add title props
  title?: string
  sessionStatus?: string
  onRetranscribe?: () => void // Callback for retranscription
  // Add speaker rename callback
  onSpeakerRename?: (oldSpeaker: string, newSpeaker: string) => void // Callback for speaker rename
}

export function TranscriptView({ 
  transcript, 
  timestamp, 
  isRecording,
  onTranscriptUpdate,
  currentPlaybackTime,
  onSeekToTime,
  title,
  sessionStatus,
  onRetranscribe,
  onSpeakerRename
}: TranscriptViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const editingCardRef = useRef<HTMLDivElement>(null)
  // State for managing edit mode and selection
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState<string>('')
  const [originalText, setOriginalText] = useState<string>('')
  const [clickTimeout, setClickTimeout] = useState<NodeJS.Timeout | null>(null)
  // Add state to track the last currently playing ID for scroll detection
  const [lastPlayingId, setLastPlayingId] = useState<string | null>(null)
  // Add state to track user-initiated seeks to prevent auto-scroll
  const [userInitiatedSeek, setUserInitiatedSeek] = useState(false)
  // Add state for toast notifications
  const [toastMessage, setToastMessage] = useState<string>('')
  const [showToast, setShowToast] = useState(false)
  // Add states for speaker editing
  const [editingSpeaker, setEditingSpeaker] = useState<string | null>(null)
  const [speakerEditText, setSpeakerEditText] = useState<string>('')
  const [originalSpeaker, setOriginalSpeaker] = useState<string>('')
  // Add states for speaker jumping
  const [speakerJumpIndices, setSpeakerJumpIndices] = useState<Record<string, number>>({})
  const [speakerClickTimeout, setSpeakerClickTimeout] = useState<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [transcript])

  // Parse timestamp for display - handles different formats
  const parseTimestamp = (timestamp: string) => {
    // Try to parse different timestamp formats
    
    // Format: [HH:MM:SS:mmm,HH:MM:SS:mmm] (time range)
    const rangeMatch = timestamp.match(/\[(\d{2}:\d{2}:\d{2}:\d{3}),(\d{2}:\d{2}:\d{2}:\d{3})\]/)
    if (rangeMatch) {
      return `${rangeMatch[1]}-${rangeMatch[2]}`
    }
    
    // Format: [HH:MM:SS:mmm] (single timestamp)
    const singleMatch = timestamp.match(/\[(\d{2}:\d{2}:\d{2}:\d{3})\]/)
    if (singleMatch) {
      return singleMatch[1]
    }
    
    // Fallback: return as is
    return timestamp
  }

  // Parse timestamp to seconds for audio sync
  const parseTimestampToSeconds = (timestamp: string): number => {
    // Try to extract the start time from different formats
    
    // Format: [HH:MM:SS:mmm,HH:MM:SS:mmm] (use start time)
    const rangeMatch = timestamp.match(/\[(\d{2}):(\d{2}):(\d{2}):(\d{3}),/)
    if (rangeMatch) {
      const hours = parseInt(rangeMatch[1])
      const minutes = parseInt(rangeMatch[2])
      const seconds = parseInt(rangeMatch[3])
      const milliseconds = parseInt(rangeMatch[4])
      return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    }
    
    // Format: [HH:MM:SS:mmm] (single timestamp)
    const singleMatch = timestamp.match(/\[(\d{2}):(\d{2}):(\d{2}):(\d{3})\]/)
    if (singleMatch) {
      const hours = parseInt(singleMatch[1])
      const minutes = parseInt(singleMatch[2])
      const seconds = parseInt(singleMatch[3])
      const milliseconds = parseInt(singleMatch[4])
      return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    }
    
    return 0 // Fallback
  }

  // Memoize getCurrentlyPlayingId to prevent recalculation on every render
  const currentlyPlayingId = useMemo(() => {
    if (!currentPlaybackTime) return null
    
    for (let i = 0; i < transcript.length; i++) {
      const item = transcript[i]
      const startTime = parseTimestampToSeconds(item.timestamp)
      
      // Get end time from next item or assume 5 seconds duration if it's the last item
      let endTime = startTime + 5 // Default 5 seconds duration
      if (i < transcript.length - 1) {
        endTime = parseTimestampToSeconds(transcript[i + 1].timestamp)
      }
      
      if (currentPlaybackTime >= startTime && currentPlaybackTime < endTime) {
        return item.id
      }
    }
    return null
  }, [currentPlaybackTime, transcript])

  // 格式化说话人显示
  const formatSpeaker = (speaker?: string) => {
    if (!speaker || speaker === 'unknown') {
      return '未识别说话人'
    }
    if (speaker === 'user') {
      return '用户'
    }
    if (speaker === 'system') {
      return '系统'
    }
    // Check if this is during real-time recording or pending speaker - show "待识别"
    if ((isRecording && speaker.startsWith('speaker')) || speaker === 'pending_speaker') {
      return '待识别'
    }
    return speaker
  }

  // Get card className based on state - memoized to prevent recalculation
  // Only one card can be highlighted at a time, with priority: editing > playing > selected
  const getCardClassName = useCallback((itemId: string) => {
    const baseClasses = "border-l-4 border-l-blue-500 shadow-sm transition-all duration-200 cursor-pointer"
    
    // Priority 1: Editing state (highest priority)
    if (editingId === itemId) {
      return `${baseClasses} ring-2 ring-blue-400 border-blue-600 bg-blue-50`
    }
    
    // Priority 2: Currently playing state (only if not editing anything)
    if (!editingId && currentlyPlayingId === itemId) {
      return `${baseClasses} bg-blue-50 border-blue-200`
    }
    
    // Priority 3: Selected state (only if not editing or playing anything)
    if (!editingId && !currentlyPlayingId && selectedId === itemId) {
      return `${baseClasses} bg-blue-50 border-blue-200`
    }
    
    // Normal state with hover effect
    return `${baseClasses} hover:ring-1 hover:ring-gray-300 hover:shadow-md hover:bg-gray-50`
  }, [editingId, currentlyPlayingId, selectedId])

  // Auto-scroll to currently playing transcript item
  useEffect(() => {
    // Only scroll if the currently playing item has changed, we're not recording, and it's not user-initiated
    if (currentlyPlayingId && currentlyPlayingId !== lastPlayingId && !isRecording && !userInitiatedSeek) {
      const playingElement = document.querySelector(`[data-transcript-id="${currentlyPlayingId}"]`) as HTMLElement
      const scrollContainer = scrollRef.current
      
      if (playingElement && scrollContainer) {
        // Use requestAnimationFrame to defer DOM operations for better performance
        requestAnimationFrame(() => {
          // Calculate the position to center the element in the viewport
          const containerRect = scrollContainer.getBoundingClientRect()
          const elementRect = playingElement.getBoundingClientRect()
          
          // Calculate the scroll position to center the element
          const containerCenter = containerRect.height / 2
          const elementTop = playingElement.offsetTop
          const elementHeight = elementRect.height
          const elementCenter = elementHeight / 2
          
          const targetScrollTop = elementTop - containerCenter + elementCenter
          
          // Smooth scroll to the target position
          scrollContainer.scrollTo({
            top: Math.max(0, targetScrollTop),
            behavior: 'smooth'
          })
        })
      }
      
      setLastPlayingId(currentlyPlayingId)
    } else if (!currentlyPlayingId) {
      setLastPlayingId(null)
    }
    
    // Reset user-initiated seek flag after the effect runs
    if (userInitiatedSeek) {
      setUserInitiatedSeek(false)
    }
  }, [currentlyPlayingId, isRecording, lastPlayingId, userInitiatedSeek])

  // Check if text has been modified
  const hasTextChanged = useCallback(() => {
    return editText.trim() !== originalText.trim()
  }, [editText, originalText])

  // Save edited text
  const saveEdit = useCallback(() => {
    if (editingId && onTranscriptUpdate) {
      const updatedTranscript = transcript.map(item => 
        item.id === editingId 
          ? { ...item, text: editText.trim() }
          : item
      )
      onTranscriptUpdate(updatedTranscript)
    }
    setEditingId(null)
    setEditText('')
    setOriginalText('')
  }, [editingId, editText, onTranscriptUpdate, transcript])

  // Cancel editing
  const cancelEdit = useCallback(() => {
    setEditingId(null)
    setEditText('')
    setOriginalText('')
  }, [])

  // Handle clicking outside edit area
  const handleClickOutsideEdit = useCallback(() => {
    if (hasTextChanged()) {
      // Ask user if they want to save changes
      const shouldSave = window.confirm('您有未保存的修改，是否需要保存？')
      if (shouldSave) {
        saveEdit()
        return
      }
    }
    // Discard changes when clicking outside
    cancelEdit()
  }, [hasTextChanged, saveEdit, cancelEdit])

  // Handle clicking outside of editing card
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (editingId && editingCardRef.current && !editingCardRef.current.contains(event.target as Node)) {
        // Clicked outside the editing card
        handleClickOutsideEdit()
      }
    }

    if (editingId) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [editingId, editText, originalText, handleClickOutsideEdit])

  // Handle clicking outside to clear selection
  useEffect(() => {
    const handleClickOutsideSelection = (event: MouseEvent) => {
      // Check if click is outside all transcript cards
      const target = event.target as Node
      const transcriptCards = document.querySelectorAll('[data-transcript-card]')
      let clickedInsideCard = false
      
      transcriptCards.forEach(card => {
        if (card.contains(target)) {
          clickedInsideCard = true
        }
      })
      
      // If clicked outside all cards and not in editing mode, clear selection
      if (!clickedInsideCard && !editingId) {
        setSelectedId(null)
      }
    }

    document.addEventListener('mousedown', handleClickOutsideSelection)

    return () => {
      document.removeEventListener('mousedown', handleClickOutsideSelection)
    }
  }, [editingId])

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (clickTimeout) {
        clearTimeout(clickTimeout)
      }
      if (speakerClickTimeout) {
        clearTimeout(speakerClickTimeout)
      }
    }
  }, [clickTimeout, speakerClickTimeout])

  // Show toast notification
  const showToastNotification = (message: string) => {
    setToastMessage(message)
    setShowToast(true)
    // Auto hide after 2 seconds
    setTimeout(() => {
      setShowToast(false)
    }, 2000)
  }

  // Copy text to clipboard
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      showToastNotification('复制成功')
    }).catch(err => {
      console.error('Failed to copy text: ', err)
      showToastNotification('复制失败')
    })
  }

  // Handle card single click (with immediate highlight and double click detection)
  const handleCardClick = (id: string, text: string, timestamp: string) => {
    if (clickTimeout) {
      // This is a double click, clear the timeout and start editing
      clearTimeout(clickTimeout)
      setClickTimeout(null)
      handleStartEdit(id, text)
    } else {
      // This is a single click - immediately select the card for instant feedback
      setSelectedId(id)
      
      // If audio sync is enabled, seek to the timestamp
      if (onSeekToTime && !isRecording) {
        // Mark this as a user-initiated seek to prevent auto-scroll
        setUserInitiatedSeek(true)
        const timeInSeconds = parseTimestampToSeconds(timestamp)
        onSeekToTime(timeInSeconds)
      }
      
      // Set up timeout to detect potential double click
      const timeout = setTimeout(() => {
        // Timeout ended, this was definitely a single click
        // Card is already selected, just cleanup
        setClickTimeout(null)
      }, 300) // 300ms window to detect double click
      setClickTimeout(timeout)
    }
  }

  // Handle starting edit mode (only through edit button)
  const handleStartEdit = (id: string, text: string) => {
    if (editingId && editingId !== id) {
      // Switching to a different card while editing
      if (hasTextChanged()) {
        const shouldSave = window.confirm('您有未保存的修改，是否需要保存？')
        if (shouldSave) {
          saveEdit()
          // After saving, start editing the new item
          setTimeout(() => startEditing(id, text), 100)
          return
        }
      }
      // Discard current changes and switch to new item
      startEditing(id, text)
    } else if (editingId === id) {
      // Already editing this card - do nothing
      return
    } else {
      // No current editing, start editing this item
      startEditing(id, text)
    }
  }

  // Start editing a transcript item
  const startEditing = (id: string, text: string) => {
    setEditingId(id)
    setEditText(text)
    setOriginalText(text)
  }

  // Handle keyboard shortcuts in edit mode
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      // Ctrl+Enter: Save edit
      e.preventDefault()
      saveEdit()
    } else if (e.key === 'Escape') {
      // Escape: Cancel edit
      e.preventDefault()
      cancelEdit()
    }
  }

  // Handle retranscription
  const handleRetranscribe = () => {
    // Show confirmation dialog before retranscription
    const confirmed = window.confirm(
      '确认重新转录？\n\n注意：\n• 此操作可能需要数分钟时间\n• 当前所有转录内容和说话人识别结果将被覆盖\n• 请确保在操作完成前不要关闭页面\n\n点击"确定"继续，或"取消"返回。'
    )
    
    if (confirmed && onRetranscribe) {
      onRetranscribe()
    }
  }

  // Handle copying all text content
  const handleCopyText = () => {
    const allText = transcript.map(item => item.text).join('\n')
    navigator.clipboard.writeText(allText).then(() => {
      showToastNotification('文本内容已复制')
    }).catch(err => {
      console.error('Failed to copy text: ', err)
      showToastNotification('复制失败')
    })
  }

  // Handle copying conversation in speaker:content format
  const handleCopyConversation = () => {
    const conversationText = transcript.map(item => {
      const speaker = formatSpeaker(item.speaker)
      return `${speaker}: ${item.text}`
    }).join('\n')
    navigator.clipboard.writeText(conversationText).then(() => {
      showToastNotification('对话内容已复制')
    }).catch(err => {
      console.error('Failed to copy text: ', err)
      showToastNotification('复制失败')
    })
  }

  // Get unique speakers from transcript with their counts
  const getUniqueSpeakers = () => {
    const speakers = transcript
      .map(item => item.speaker)
      .filter(Boolean)
      .filter(speaker => speaker !== 'unknown') as string[]
    return Array.from(new Set(speakers))
  }

  // Get speaker count for a specific speaker
  const getSpeakerCount = (speaker: string) => {
    return transcript.filter(item => item.speaker === speaker).length
  }

  // Handle speaker tag double click
  const handleSpeakerTagDoubleClick = (speaker: string) => {
    setEditingSpeaker(speaker)
    setSpeakerEditText(speaker)
    setOriginalSpeaker(speaker)
  }

  // Save speaker rename
  const saveSpeakerRename = () => {
    if (editingSpeaker && speakerEditText.trim() !== '' && speakerEditText.trim() !== originalSpeaker) {
      // Call speaker rename callback to update database
      if (onSpeakerRename) {
        onSpeakerRename(editingSpeaker, speakerEditText.trim())
      }
      
      showToastNotification('说话人名称已更新')
    }
    
    // Reset editing state
    setEditingSpeaker(null)
    setSpeakerEditText('')
    setOriginalSpeaker('')
  }

  // Cancel speaker rename
  const cancelSpeakerRename = () => {
    setEditingSpeaker(null)
    setSpeakerEditText('')
    setOriginalSpeaker('')
  }

  // Handle speaker rename key down
  const handleSpeakerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      saveSpeakerRename()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      cancelSpeakerRename()
    }
  }

  // Handle speaker tag click to jump to next occurrence (with delay to handle double click)
  const handleSpeakerTagClick = (speaker: string) => {
    if (speakerClickTimeout) {
      // This is a double click, clear the timeout and don't execute single click
      clearTimeout(speakerClickTimeout)
      setSpeakerClickTimeout(null)
      return
    }
    
    // Set timeout for single click
    const timeout = setTimeout(() => {
      // Find all transcript items with this speaker
      const speakerItems = transcript
        .map((item, index) => ({ ...item, originalIndex: index }))
        .filter(item => item.speaker === speaker)
      
      if (speakerItems.length === 0) return
      
      // Get current jump index for this speaker (default to -1 for first click)
      const currentIndex = speakerJumpIndices[speaker] ?? -1
      
      // Calculate next index (cycle through all occurrences)
      const nextIndex = (currentIndex + 1) % speakerItems.length
      
      // Update speaker jump indices - clear other speakers' indices when switching
      setSpeakerJumpIndices({
        [speaker]: nextIndex
      })
      
      // Get the target item
      const targetItem = speakerItems[nextIndex]
      
      // Select the target card
      setSelectedId(targetItem.id)
      
      // Scroll to the target card
      const targetElement = document.querySelector(`[data-transcript-id="${targetItem.id}"]`) as HTMLElement
      const scrollContainer = scrollRef.current
      
      if (targetElement && scrollContainer) {
        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(() => {
          // Calculate the position to center the element in the viewport
          const containerRect = scrollContainer.getBoundingClientRect()
          const elementTop = targetElement.offsetTop
          const elementHeight = targetElement.getBoundingClientRect().height
          
          // Calculate scroll position to center the element
          const containerCenter = containerRect.height / 2
          const elementCenter = elementHeight / 2
          const targetScrollTop = elementTop - containerCenter + elementCenter
          
          // Smooth scroll to the target position
          scrollContainer.scrollTo({
            top: Math.max(0, targetScrollTop),
            behavior: 'smooth'
          })
        })
      }
      
      // Show toast notification with current position
      showToastNotification(`已跳转到 ${speaker} 的第 ${nextIndex + 1}/${speakerItems.length} 条记录`)
      
      // Clear timeout
      setSpeakerClickTimeout(null)
    }, 300) // 300ms delay to detect double click
    
    setSpeakerClickTimeout(timeout)
  }

  return (
    <div className="h-full bg-white overflow-hidden flex-shrink relative">
      {/* Toast Notification */}
      {showToast && (
        <div className="absolute top-4 right-4 z-50 bg-green-500 text-white px-4 py-2 rounded-md shadow-lg transition-all duration-300 ease-in-out">
          <div className="flex items-center space-x-2">
            <Check className="h-4 w-4" />
            <span className="text-sm font-medium">{toastMessage}</span>
          </div>
        </div>
      )}
      
      <div className="h-full flex flex-col">
        {/* Title Header */}
        <div className="px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-semibold text-gray-900 break-words leading-tight flex-1">
              {title || (isRecording ? "录音中..." : "新建录音")}
            </h1>
            {/* Action buttons for completed sessions */}
            {sessionStatus === 'completed' && transcript && transcript.length > 0 && (
              <div className="flex items-center space-x-2 ml-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleRetranscribe}
                  className="h-8 px-2 hover:bg-blue-100"
                  title="重新转录"
                >
                  <RefreshCw className="h-4 w-4 text-gray-600" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopyText}
                  className="h-8 px-2 hover:bg-blue-100"
                  title="复制文本内容"
                >
                  <Copy className="h-4 w-4 text-gray-600" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopyConversation}
                  className="h-8 px-2 hover:bg-blue-100"
                  title="复制对话"
                >
                  <FileText className="h-4 w-4 text-gray-600" />
                </Button>
              </div>
            )}
          </div>
          {timestamp && (
            <p className="text-sm text-gray-500 mt-1">
              创建时间: {timestamp}
            </p>
          )}
          {/* Show reprocessing status for completed sessions */}
          {sessionStatus === 'processing' && (
            <div className="mt-2 px-3 py-2 bg-blue-50 border border-blue-200 rounded-md">
              <div className="flex items-center space-x-2">
                <div className="flex space-x-1">
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
                <span className="text-sm text-blue-700 font-medium">正在重新识别说话人和内容...</span>
              </div>
              <p className="text-xs text-blue-600 mt-1">这可能需要几分钟时间，请耐心等待</p>
            </div>
          )}
          
          {/* Show completion status hint with speaker tags */}
          {sessionStatus === 'completed' && transcript && transcript.length > 0 && (
            <div className="mt-2 px-3 py-2 bg-green-50 border border-green-200 rounded-md">
              <div className="flex items-center space-x-2 mb-2">
                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                <span className="text-sm text-green-700 font-medium">
                  说话人识别完成，识别到 {getUniqueSpeakers().length} 个不同说话人
                </span>
              </div>
              {/* Speaker tags */}
              {getUniqueSpeakers().length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  <span className="text-xs text-green-600 mr-2">说话人标签：</span>
                  {getUniqueSpeakers().map((speaker) => (
                    <div key={speaker} className="relative">
                      {editingSpeaker === speaker ? (
                        <div className="flex items-center space-x-1">
                          <input
                            type="text"
                            value={speakerEditText}
                            onChange={(e) => setSpeakerEditText(e.target.value)}
                            onKeyDown={handleSpeakerKeyDown}
                            onBlur={saveSpeakerRename}
                            className="text-xs px-2 py-1 bg-white border border-blue-400 rounded-full focus:outline-none focus:ring-1 focus:ring-blue-500 min-w-[80px]"
                            autoFocus
                            onClick={(e) => e.stopPropagation()}
                          />
                          <button
                            onClick={saveSpeakerRename}
                            className="text-green-600 hover:text-green-700"
                            title="保存"
                          >
                            <Check className="h-3 w-3" />
                          </button>
                          <button
                            onClick={cancelSpeakerRename}
                            className="text-red-600 hover:text-red-700"
                            title="取消"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      ) : (
                        <span
                          className="inline-flex items-center px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full cursor-pointer hover:bg-blue-200 transition-colors"
                          onClick={() => handleSpeakerTagClick(speaker)}
                          onDoubleClick={() => handleSpeakerTagDoubleClick(speaker)}
                          title="单击跳转到该说话人，双击编辑说话人名称"
                        >
                          {speaker} ({getSpeakerCount(speaker)})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <p className="text-xs text-green-600 mt-1">单击说话人标签跳转，双击可以重命名</p>
            </div>
          )}
        </div>

        {/* Transcript Content */}
        <div className="flex-1 p-4 min-h-0">
          <div 
            ref={scrollRef}
            className="h-full overflow-y-auto space-y-2 min-h-0"
          >
            {transcript.map((item) => (
              <Card 
                key={item.id} 
                ref={editingId === item.id ? editingCardRef : null}
                className={getCardClassName(item.id)}
                data-transcript-card="true"
                data-transcript-id={item.id}
                onClick={() => {
                  // Handle single/double click detection
                  if (!isRecording) {
                    handleCardClick(item.id, item.text, item.timestamp)
                  }
                }}
              >
                <CardContent className="p-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      {/* Header with Speaker and Time */}
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2">
                          {/* Speaker Icon and Name - 使用真实数据 */}
                          <div className="flex items-center space-x-1">
                            <User className="h-3 w-3 text-gray-500" />
                            <span className="text-xs font-medium text-gray-700">
                              {formatSpeaker(item.speaker)}
                            </span>
                          </div>
                          {/* Time - 使用真实的时间戳数据 */}
                          <span className="text-xs text-gray-500">
                            {parseTimestamp(item.timestamp)}
                          </span>
                        </div>
                        
                        {/* Action Icons */}
                        <div className="flex items-center space-x-1">
                          {editingId === item.id ? (
                            // Edit mode buttons
                            <>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6 hover:bg-green-100"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  saveEdit()
                                }}
                                title="保存 (Ctrl+Enter)"
                              >
                                <Check className="h-3 w-3 text-green-600" />
                              </Button>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6 hover:bg-red-100"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  cancelEdit()
                                }}
                                title="取消 (Esc)"
                              >
                                <X className="h-3 w-3 text-red-600" />
                              </Button>
                            </>
                          ) : (
                            // View mode buttons
                            <>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6 hover:bg-gray-100"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  copyToClipboard(item.text)
                                }}
                                title="复制"
                              >
                                <Copy className="h-3 w-3 text-gray-500" />
                              </Button>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6 hover:bg-gray-100"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  if (!isRecording) {
                                    handleStartEdit(item.id, item.text)
                                  }
                                }}
                                title="编辑"
                              >
                                <Edit3 className="h-3 w-3 text-gray-500" />
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                      
                      {/* Content Text or Edit Input */}
                      {editingId === item.id ? (
                        <Textarea
                          value={editText}
                          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setEditText(e.target.value)}
                          onKeyDown={handleKeyDown}
                          onClick={(e: React.MouseEvent) => e.stopPropagation()}
                          className="text-sm resize-none min-h-[60px] focus:ring-2 focus:ring-blue-400"
                          placeholder="编辑转录内容..."
                          autoFocus
                        />
                      ) : (
                        <p className="text-gray-900 leading-relaxed text-sm">
                          {item.text}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            {transcript.length === 0 && !isRecording && (
              <div className="text-center py-8">
                <p className="text-gray-500 text-sm">暂无转录内容</p>
              </div>
            )}

            {isRecording && (
              <div className="flex items-center justify-center py-3">
                <div className="flex space-x-1">
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="ml-2 text-xs text-gray-500">正在转录...</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
} 