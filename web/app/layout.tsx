import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { AuthProvider } from '@/hooks/useAuth'
import { ErrorBoundary } from '@/components/error-boundary'
import { Toaster } from 'sonner'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Voice Transcription Assistant - Real-time Speech to Text with AI Summary',
  description: 'Real-time voice transcription web application built with Next.js + FastRTC, supporting AI intelligent summary',
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