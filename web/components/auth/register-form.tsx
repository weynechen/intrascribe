'use client'

import { useState } from 'react'
import { Eye, EyeOff, Mail, Lock, User, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useAuth } from '@/hooks/useAuth'
import { SocialLoginButtons } from './social-login-buttons'

interface RegisterFormProps {
  onToggleMode: () => void
}

export function RegisterForm({ onToggleMode }: RegisterFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  
  const { signUp } = useAuth()

  const passwordsMatch = password === confirmPassword
  const isFormValid = email && password && confirmPassword && username && passwordsMatch && password.length >= 6

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isFormValid) return

    setIsLoading(true)
    setError(null)
    setSuccess(null)
    try {
      await signUp(email, password, username, fullName || undefined)
      setSuccess('账户创建成功！请检查您的邮箱以验证账户。')
    } catch (err: unknown) {
      const error = err as { message?: string }
      console.error('注册错误详情:', err)
      
      // 处理特定的错误类型
      let errorMessage = '注册失败，请重试'
      
      if (error.message) {
        if (error.message.includes('duplicate key value violates unique constraint "users_username_key"') ||
            error.message.includes('username') && error.message.includes('already exists')) {
          errorMessage = `用户名 "${username}" 已被占用，请选择其他用户名`
        } else if (error.message.includes('duplicate key value violates unique constraint "users_email_key"') ||
                   error.message.includes('email') && error.message.includes('already exists')) {
          errorMessage = `邮箱 "${email}" 已被注册，请使用其他邮箱或尝试登录`
        } else if (error.message.includes('User already registered')) {
          errorMessage = '该邮箱已注册，请直接登录'
        } else if (error.message.includes('Password should be at least 6 characters')) {
          errorMessage = '密码长度至少需要6个字符'
        } else if (error.message.includes('Invalid email')) {
          errorMessage = '邮箱格式不正确'
        } else {
          errorMessage = error.message
        }
      }
      
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Create Account</h1>
        <p className="text-muted-foreground">
          Join us and start transcribing your audio files
        </p>
      </div>

      {/* 错误和成功消息 */}
      {error && (
        <div className="p-3 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg">
          {error}
        </div>
      )}
      {success && (
        <div className="p-3 text-sm text-green-600 bg-green-50 border border-green-200 rounded-lg">
          {success}
        </div>
      )}

      {/* 社交登录按钮 */}
      <SocialLoginButtons />

      {/* 分隔线 */}
      <div className="relative">
        <Separator />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="bg-background px-2 text-xs text-muted-foreground">
            OR REGISTER WITH EMAIL
          </span>
        </div>
      </div>

      {/* 注册表单 */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* 用户名输入 */}
        <div className="space-y-2">
          <Label htmlFor="username">Username *</Label>
          <div className="relative">
            <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="username"
              type="text"
              placeholder="Choose a username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="pl-10"
              required
              disabled={isLoading}
            />
          </div>
        </div>

        {/* 全名输入 */}
        <div className="space-y-2">
          <Label htmlFor="fullName">Full Name (Optional)</Label>
          <div className="relative">
            <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="fullName"
              type="text"
              placeholder="Enter your full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="pl-10"
              disabled={isLoading}
            />
          </div>
        </div>

        {/* 邮箱输入 */}
        <div className="space-y-2">
          <Label htmlFor="register-email">Email *</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="register-email"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="pl-10"
              required
              disabled={isLoading}
            />
          </div>
        </div>

        {/* 密码输入 */}
        <div className="space-y-2">
          <Label htmlFor="register-password">Password *</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="register-password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Create a password (min. 6 characters)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="pl-10 pr-10"
              required
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-3 text-muted-foreground hover:text-foreground"
              disabled={isLoading}
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
          {password && password.length < 6 && (
            <p className="text-xs text-destructive">
              Password must be at least 6 characters long
            </p>
          )}
        </div>

        {/* 确认密码输入 */}
        <div className="space-y-2">
          <Label htmlFor="confirm-password">Confirm Password *</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="confirm-password"
              type={showConfirmPassword ? 'text' : 'password'}
              placeholder="Confirm your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="pl-10 pr-10"
              required
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3 top-3 text-muted-foreground hover:text-foreground"
              disabled={isLoading}
            >
              {showConfirmPassword ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
          {confirmPassword && !passwordsMatch && (
            <p className="text-xs text-destructive">
              Passwords do not match
            </p>
          )}
        </div>

        {/* 注册按钮 */}
        <Button 
          type="submit" 
          className="w-full" 
          disabled={isLoading || !isFormValid}
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Creating account...
            </>
          ) : (
            'Create Account'
          )}
        </Button>
      </form>

      {/* 登录链接 */}
      <div className="text-center text-sm">
        <span className="text-muted-foreground">Already have an account? </span>
        <button
          onClick={onToggleMode}
          className="text-primary hover:underline font-medium"
          disabled={isLoading}
        >
          Sign In
        </button>
      </div>
    </div>
  )
} 