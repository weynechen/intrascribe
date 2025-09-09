'use client'

import { useState } from 'react'
import { Eye, EyeOff, Mail, Lock, User, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useAuth } from '@/hooks/useAuth'

interface RegisterFormProps {
  onToggleMode: () => void
}

export function RegisterForm({ onToggleMode }: RegisterFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [username, setUsername] = useState('')
  // const [fullName, _setFullName] = useState('')
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
      await signUp(email, password, username, undefined)
      setSuccess('Account created successfully! Please check your email to verify your account.')
    } catch (err: unknown) {
      const error = err as { message?: string }
      
      // Handle specific error types
      let errorMessage = 'Registration failed, please try again'
      
      if (error.message) {
        if (error.message.includes('duplicate key value violates unique constraint "users_username_key"') ||
            error.message.includes('username') && error.message.includes('already exists')) {
          errorMessage = `Username "${username}" is already taken, please choose another username`
        } else if (error.message.includes('duplicate key value violates unique constraint "users_email_key"') ||
                   error.message.includes('email') && error.message.includes('already exists')) {
          errorMessage = `Email "${email}" is already registered, please use another email or try logging in`
        } else if (error.message.includes('User already registered')) {
          errorMessage = 'This email is already registered, please login directly'
        } else if (error.message.includes('Password should be at least 6 characters')) {
          errorMessage = 'Password must be at least 6 characters long'
        } else if (error.message.includes('Invalid email')) {
          errorMessage = 'Email format is incorrect'
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
      {/* Title */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Create Account</h1>
        <p className="text-muted-foreground">
          Join us and start transcribing your audio files
        </p>
      </div>

      {/* Error and success messages */}
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

      {/* Social login buttons */}
      {/* <SocialLoginButtons /> */}

      {/* Divider */}
      <div className="relative">
        <Separator />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="bg-background px-2 text-xs text-muted-foreground">
            OR REGISTER WITH EMAIL
          </span>
        </div>
      </div>

      {/* Registration form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Username input */}
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

        {/* Full name input */}
        {/* <div className="space-y-2">
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
        </div> */}

        {/* Email input */}
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

        {/* Password input */}
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

        {/* Confirm password input */}
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

        {/* Register button */}
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

      {/* Login link */}
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