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
        // Handle OAuth callback
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
          // Delayed redirect to avoid race conditions
          setTimeout(() => {
            router.replace('/auth?error=callback_error')
          }, 100)
          return
        }

        if (data.session) {
          // Login successful, delayed redirect to main page
          setTimeout(() => {
            router.replace('/')
          }, 100)
        } else {
          // No session, delayed redirect to login page
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

    // Delayed callback handling to ensure component is fully mounted
    const timeoutId = setTimeout(handleAuthCallback, 200)
    
    return () => clearTimeout(timeoutId)
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="text-center space-y-4">
        <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
        <p className="text-muted-foreground">Processing login...</p>
      </div>
    </div>
  )
} 