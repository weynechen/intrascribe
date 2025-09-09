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

  // Email password login
  const signIn = async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    
    if (error) {
      throw error
    }
    
    // Don't return data, keep consistent with interface definition
  }

  // Email password registration
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
    
    // Don't return data, keep consistent with interface definition
  }

  // Logout
  const signOut = async () => {
    const { error } = await supabase.auth.signOut()
    
    if (error) {
      throw error
    }
  }

  // Third-party login
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
    
    // Don't return data, keep consistent with interface definition
  }

  // Reset password
  const resetPassword = async (email: string) => {
    const { data, error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/reset-password`
    })
    
    return { data, error }
  }

  useEffect(() => {
    // Use ref to ensure initialization only once
    if (initializedRef.current) {
      return
    }

    initializedRef.current = true
    let mounted = true
    let subscription: any = null

    // Get initial session
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

    // Listen to auth state changes
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
  }, []) // Empty dependency array, run only once

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