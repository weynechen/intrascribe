import { createClient as supabaseCreateClient } from '@supabase/supabase-js'
import { cookies } from 'next/headers'

export async function createClient() {
  const supabaseUrl = 'http://localhost:3000/supabase'
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

  if (!supabaseAnonKey) {
    throw new Error('Missing NEXT_PUBLIC_SUPABASE_ANON_KEY environment variable')
  }

  const cookieStore = await cookies()

  return supabaseCreateClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
      detectSessionInUrl: false,
      storage: {
        getItem: (key: string) => {
          return cookieStore.get(key)?.value || null
        },
        setItem: (key: string, value: string) => {
          cookieStore.set(key, value)
        },
        removeItem: (key: string) => {
          cookieStore.delete(key)
        },
      },
    },
  })
} 