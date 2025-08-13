import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { AuthProvider } from '@/hooks/useAuth'
import { ErrorBoundary } from '@/components/error-boundary'
import { Toaster } from 'sonner'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: '语音转录助手 - 实时语音转文字AI总结',
  description: '基于 Next.js + FastRTC 构建的实时语音转录Web应用，支持AI智能总结',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className={inter.className} suppressHydrationWarning>
        <ErrorBoundary>
          <AuthProvider>
            {children}
            <Toaster 
              position="bottom-right"
              richColors
              closeButton
              duration={4000}
              visibleToasts={5}
            />
          </AuthProvider>
        </ErrorBoundary>
      </body>
    </html>
  )
} 