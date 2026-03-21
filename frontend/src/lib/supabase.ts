import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl  = import.meta.env.VITE_SUPABASE_URL  || ''
const supabaseAnon = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

// Supabase client — only create if URL is configured, otherwise null
export const supabase: SupabaseClient | null =
  supabaseUrl ? createClient(supabaseUrl, supabaseAnon) : null

export async function getSession() {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session
}

export async function getAccessToken(): Promise<string | null> {
  const session = await getSession()
  return session?.access_token ?? null
}

export async function signOut() {
  if (supabase) await supabase.auth.signOut()
}
