import { http } from './client'

export interface AuthUser {
  user_id: string
  email: string
  display_name: string
  status: string
  email_verified: boolean
  created_at?: string
}

export interface AuthSession {
  user: AuthUser
  access_token: string
  refresh_token: string
  token_type: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export function registerUser(payload: { email: string; password: string; display_name?: string }) {
  return http.post<AuthSession>('/api/auth/register', payload)
}

export function loginUser(payload: { email: string; password: string }) {
  return http.post<AuthSession>('/api/auth/login', payload)
}

export function refreshTokens(refresh_token: string) {
  return http.post<TokenPair>('/api/auth/refresh', { refresh_token })
}

export function getMe() {
  return http.get<AuthUser>('/api/auth/me')
}

export function forgotPassword(email: string) {
  return http.post<{ message: string }>('/api/auth/forgot-password', { email })
}

export function resetPassword(token: string, new_password: string) {
  return http.post<{ message: string }>('/api/auth/reset-password', { token, new_password })
}

export function verifyEmail(token: string) {
  return http.post<{ message: string }>('/api/auth/verify-email', { token })
}

export function resendVerification() {
  return http.post<{ message: string }>('/api/auth/resend-verification', {})
}
