'use client'

import { createContext, useContext, useEffect, useState, ReactNode, useRef } from 'react'
import { supabase } from '@/lib/supabase'
import type { User, Session, AuthChangeEvent } from '@supabase/supabase-js'

interface AuthContextType {
  user: User | null
  session: Session | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, username?: string, fullName?: string) => Promise<void>
  signOut: () => Promise<void>
  signInWithProvider: (provider: 'google' | 'github') => Promise<void>
  resetPassword: (email: string) => Promise<{ data?: any; error?: any }>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  session: null,
  loading: true,
  signIn: async () => {},
  signUp: async () => {},
  signOut: async () => {},
  signInWithProvider: async () => {},
  resetPassword: async () => ({ error: null }),
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const initializedRef = useRef(false)

  // 邮箱密码登录
  const signIn = async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    
    if (error) {
      throw error
    }
    
    // 不返回数据，保持与接口定义一致
  }

  // 邮箱密码注册
  const signUp = async (email: string, password: string, username?: string, fullName?: string) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          username: username,
          full_name: fullName,
        }
      }
    })
    
    if (error) {
      throw error
    }
    
    // 不返回数据，保持与接口定义一致
  }

  // 登出
  const signOut = async () => {
    const { error } = await supabase.auth.signOut()
    
    if (error) {
      throw error
    }
  }

  // 第三方登录
  const signInWithProvider = async (provider: 'google' | 'github') => {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/auth/callback`
      }
    })
    
    if (error) {
      throw error
    }
    
    // 不返回数据，保持与接口定义一致
  }

  // 重置密码
  const resetPassword = async (email: string) => {
    const { data, error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/reset-password`
    })
    
    return { data, error }
  }

  useEffect(() => {
    // 使用 ref 确保只初始化一次
    if (initializedRef.current) {
      return
    }

    initializedRef.current = true
    let mounted = true
    let subscription: any = null

    // 获取初始会话
    const initAuth = async () => {
      try {
        const { data: { session: initialSession }, error } = await supabase.auth.getSession()
        
        if (error) {
          console.error('Failed to get initial session:', error)
        }
        
        if (mounted) {
          setSession(initialSession)
          setUser(initialSession?.user ?? null)
          setLoading(false)
        }
      } catch (error) {
        console.error('Auth initialization failed:', error)
        if (mounted) {
          setLoading(false)
        }
      }
    }

    // 监听认证状态变化
    try {
      const { data } = supabase.auth.onAuthStateChange(
        (event: AuthChangeEvent, currentSession: Session | null) => {
          if (mounted) {
            console.log('Auth event:', event)
            setSession(currentSession)
            setUser(currentSession?.user ?? null)
            if (loading) {
              setLoading(false)
            }
          }
        }
      )
      subscription = data.subscription
    } catch (error) {
      console.error('Failed to set up auth state listener:', error)
    }

    initAuth()

    return () => {
      mounted = false
      try {
        subscription?.unsubscribe()
      } catch (error) {
        console.error('Failed to unsubscribe from auth state changes:', error)
      }
    }
  }, []) // 空依赖数组，只运行一次

  return (
    <AuthContext.Provider value={{ 
      user, 
      session, 
      loading, 
      signIn, 
      signUp, 
      signOut, 
      signInWithProvider, 
      resetPassword
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
} 