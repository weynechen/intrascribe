'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { Loader2 } from 'lucide-react'

export default function AuthCallback() {
  const router = useRouter()

  useEffect(() => {
    const handleAuthCallback = async () => {
      try {
        // 处理 OAuth 回调
        if (!supabase) {
          console.error('Supabase client not initialized')
          setTimeout(() => {
            router.replace('/auth?error=client_error')
          }, 100)
          return
        }
        
        const { data, error } = await supabase.auth.getSession()
        
        if (error) {
          console.error('Auth callback error:', error)
          // 延迟重定向以避免竞争条件
          setTimeout(() => {
            router.replace('/auth?error=callback_error')
          }, 100)
          return
        }

        if (data.session) {
          // 登录成功，延迟重定向到主页面
          setTimeout(() => {
            router.replace('/')
          }, 100)
        } else {
          // 没有会话，延迟重定向到登录页面
          setTimeout(() => {
            router.replace('/auth')
          }, 100)
        }
      } catch (error) {
        console.error('Unexpected error during auth callback:', error)
        setTimeout(() => {
          router.replace('/auth?error=unexpected_error')
        }, 100)
      }
    }

    // 延迟执行回调处理以确保组件完全挂载
    const timeoutId = setTimeout(handleAuthCallback, 200)
    
    return () => clearTimeout(timeoutId)
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="text-center space-y-4">
        <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
        <p className="text-muted-foreground">正在处理登录...</p>
      </div>
    </div>
  )
} 