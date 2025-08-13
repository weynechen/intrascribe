'use client'

import { useState } from 'react'
import { ArrowLeft, Mail, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'

interface ForgotPasswordFormProps {
  onBack: () => void
}

export function ForgotPasswordForm({ onBack }: ForgotPasswordFormProps) {
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  
  const { resetPassword } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return

    setIsLoading(true)
    try {
      const { error } = await resetPassword(email)
      if (!error) {
        setIsSuccess(true)
      }
    } finally {
      setIsLoading(false)
    }
  }

  if (isSuccess) {
    return (
      <div className="space-y-6">
        <div className="text-center space-y-4">
          <div className="mx-auto w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center">
            <Mail className="w-6 h-6 text-primary" />
          </div>
          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight">Check Your Email</h1>
            <p className="text-muted-foreground">
              We&apos;ve sent a password reset link to{' '}
              <span className="font-medium text-foreground">{email}</span>
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <Button onClick={onBack} className="w-full">
            Back to Sign In
          </Button>
          <div className="text-center text-sm text-muted-foreground">
            Didn&apos;t receive the email? Check your spam folder or{' '}
            <button
              onClick={() => {
                setIsSuccess(false)
                setEmail('')
              }}
              className="text-primary hover:underline"
            >
              try again
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 返回按钮和标题 */}
      <div className="space-y-4">
        <button
          onClick={onBack}
          className="flex items-center text-sm text-muted-foreground hover:text-foreground"
          disabled={isLoading}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Sign In
        </button>
        
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Forgot Password?</h1>
          <p className="text-muted-foreground">
            No worries! Enter your email and we&apos;ll send you a reset link.
          </p>
        </div>
      </div>

      {/* 重置密码表单 */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="reset-email">Email</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="reset-email"
              type="email"
              placeholder="Enter your email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="pl-10"
              required
              disabled={isLoading}
            />
          </div>
        </div>

        <Button 
          type="submit" 
          className="w-full" 
          disabled={isLoading || !email}
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Sending reset link...
            </>
          ) : (
            'Send Reset Link'
          )}
        </Button>
      </form>
    </div>
  )
} 