'use client'

// Extend window object for global audio player control
declare global {
  interface Window {
    audioPlayerSeekTo?: (time: number) => void
  }
}

import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Play, Pause } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'

interface AudioPlayerProps {
  audioUrl?: string
  isVisible: boolean
  className?: string
  onTimeUpdate?: (currentTime: number) => void
  onSeekTo?: (time: number) => void
}

export function AudioPlayer({ 
  audioUrl, 
  isVisible, 
  className = '',
  onTimeUpdate,
  onSeekTo
}: AudioPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string>()
  
  const audioRef = useRef<HTMLAudioElement>(null)
  const lastUpdateTimeRef = useRef<number>(0)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const updateTime = () => {
      const time = audio.currentTime
      const now = Date.now()
      
      // Always update internal state for smooth UI progress bar
      setCurrentTime(time)
      
      // Only trigger onTimeUpdate callback every 1+ seconds to reduce re-renders
      if (onTimeUpdate && (now - lastUpdateTimeRef.current >= 1000)) {
        onTimeUpdate(time)
        lastUpdateTimeRef.current = now
      }
    }
    const updateDuration = () => {
      setDuration(audio.duration || 0)
    }
    const handleLoadStart = () => {
      setIsLoading(true)
      setError(undefined)
    }
    const handleCanPlay = () => {
      setIsLoading(false)
    }
    const handleEnded = () => {
      setIsPlaying(false)
    }
    const handleError = (e: Event) => {
      const audioElement = e.target as HTMLAudioElement
      if (audioElement.error) {
        const errorMessage = `音频错误 ${audioElement.error.code}: ${audioElement.error.message}`
        setError(errorMessage)
      }
      setIsLoading(false)
    }

    audio.addEventListener('timeupdate', updateTime)
    audio.addEventListener('loadedmetadata', updateDuration)
    audio.addEventListener('loadstart', handleLoadStart)
    audio.addEventListener('canplay', handleCanPlay)
    audio.addEventListener('ended', handleEnded)
    audio.addEventListener('error', handleError)

    return () => {
      audio.removeEventListener('timeupdate', updateTime)
      audio.removeEventListener('loadedmetadata', updateDuration)
      audio.removeEventListener('loadstart', handleLoadStart)
      audio.removeEventListener('canplay', handleCanPlay)
      audio.removeEventListener('ended', handleEnded)
      audio.removeEventListener('error', handleError)
    }
  }, [audioUrl, onTimeUpdate])

  // Remove unused volume effect

  const togglePlayPause = async () => {
    const audio = audioRef.current
    if (!audio || !audioUrl) {
      return
    }

    try {
      if (isPlaying) {
        audio.pause()
        setIsPlaying(false)
      } else {
        await audio.play()
        setIsPlaying(true)
      }
    } catch (error) {
      setError(`播放失败: ${error}`)
    }
  }

  const handleProgressChange = (values: number[]) => {
    const audio = audioRef.current
    if (!audio || !duration) return

    const newTime = (values[0] / 100) * duration
    audio.currentTime = newTime
    setCurrentTime(newTime)
  }

  const formatTime = (time: number): string => {
    if (isNaN(time)) return '0:00'
    
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  // Remove unused skipTime function
  // const skipTime = (seconds: number) => {
  //   const audio = audioRef.current
  //   if (!audio) return
  //   audio.currentTime = Math.max(0, Math.min(duration, currentTime + seconds))
  // }

  const seekTo = useCallback((time: number) => {
    const audio = audioRef.current
    if (audio && duration > 0) {
      const targetTime = Math.max(0, Math.min(duration, time))
      audio.currentTime = targetTime
      setCurrentTime(targetTime)
    }
  }, [duration])

  useEffect(() => {
    if (onSeekTo) {
      window.audioPlayerSeekTo = seekTo
      
      return () => {
        if (window.audioPlayerSeekTo === seekTo) {
          delete window.audioPlayerSeekTo
        }
      }
    }
  }, [seekTo, duration, onSeekTo])

  if (!isVisible) return null

  return (
    <div className={`${className}`}>
      <audio ref={audioRef} src={audioUrl} preload="metadata" />
      
      {/* 错误显示 */}
      {error && (
        <div className="text-xs text-red-500 bg-red-50 px-2 py-1 rounded mb-2">
          {error}
        </div>
      )}
      
      {/* 优化布局容器 - 播放按钮靠左，进度条水平铺满 */}
      <div className="flex items-center space-x-3 w-full">
        {/* 播放控制按钮 - 固定在左侧 */}
        <div className="flex-shrink-0">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8"
            onClick={togglePlayPause}
            disabled={!audioUrl || isLoading}
          >
            {isLoading ? (
              <div className="h-4 w-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin" />
            ) : isPlaying ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* 进度条和时间 - 占据剩余空间 */}
        <div className="flex items-center space-x-2 flex-1 min-w-0">
          <span className="text-xs text-gray-500 flex-shrink-0 w-10 text-right">
            {formatTime(currentTime)}
          </span>
          
          <div className="flex-1 min-w-0">
            <Slider
              value={[duration ? (currentTime / duration) * 100 : 0]}
              onValueChange={handleProgressChange}
              max={100}
              step={0.1}
              className="cursor-pointer w-full"
              disabled={!audioUrl || isLoading}
            />
          </div>
          
          <span className="text-xs text-gray-500 flex-shrink-0 w-10">
            {formatTime(duration)}
          </span>
        </div>
      </div>
    </div>
  )
} 