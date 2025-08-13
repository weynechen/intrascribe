'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Mic } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { LoginForm } from '@/components/auth/login-form'
import { RegisterForm } from '@/components/auth/register-form'
import { ForgotPasswordForm } from '@/components/auth/forgot-password-form'
import { useAuth } from '@/hooks/useAuth'

type AuthMode = 'login' | 'register' | 'forgot-password'

export default function AuthPage() {
  const [mode, setMode] = useState<AuthMode>('login')
  const router = useRouter()
  const { user, loading } = useAuth()

  // 如果用户已登录，跳转到主页面
  useEffect(() => {
    if (!loading && user) {
      router.push('/')
    }
  }, [user, loading, router])

  // 如果正在加载或已登录，显示加载状态
  if (loading || user) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center p-4">
        <div className="text-center">
          <div className="mx-auto w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mb-4 animate-pulse">
            <Mic className="w-8 h-8 text-primary-foreground" />
          </div>
          <p className="text-muted-foreground">正在跳转...</p>
        </div>
      </div>
    )
  }

  const renderForm = () => {
    switch (mode) {
      case 'login':
        return (
          <LoginForm
            onToggleMode={() => setMode('register')}
            onForgotPassword={() => setMode('forgot-password')}
          />
        )
      case 'register':
        return (
          <RegisterForm
            onToggleMode={() => setMode('login')}
          />
        )
      case 'forgot-password':
        return (
          <ForgotPasswordForm
            onBack={() => setMode('login')}
          />
        )
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-8">
        {/* Logo */}
        <div className="text-center">
          <div className="mx-auto w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mb-4">
            <Mic className="w-8 h-8 text-primary-foreground" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">
            ASR FastRTC
          </h2>
          <p className="text-sm text-muted-foreground">
            Real-time Audio Transcription
          </p>
        </div>

        {/* Authentication Form */}
        <Card className="border-0 shadow-xl">
          <CardContent className="p-8">
            {renderForm()}
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center text-xs text-muted-foreground space-y-1">
          <p>
            By continuing, you agree to our{' '}
            <a href="/terms" className="text-primary hover:underline">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="/privacy" className="text-primary hover:underline">
              Privacy Policy
            </a>
          </p>
        </div>
      </div>
    </div>
  )
} 