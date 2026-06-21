import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import {
  getMe,
  loginUser,
  registerUser,
  resendVerification as apiResendVerification,
  type AuthUser,
} from '@/lib/api/auth'
import { setUnauthorizedHandler } from '@/lib/api/client'
import { clearTokens, getAccessToken, setTokens } from '@/lib/auth-storage'

type AuthMode = 'login' | 'register' | 'forgot'

interface AuthContextValue {
  user: AuthUser | null
  ready: boolean
  isAuthenticated: boolean
  dialogOpen: boolean
  dialogMode: AuthMode
  openAuth: (mode?: AuthMode) => void
  closeAuth: () => void
  setDialogMode: (mode: AuthMode) => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  resendVerification: () => Promise<string>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [ready, setReady] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<AuthMode>('login')
  const bootstrapped = useRef(false)

  const openAuth = useCallback((mode: AuthMode = 'login') => {
    setDialogMode(mode)
    setDialogOpen(true)
  }, [])
  const closeAuth = useCallback(() => setDialogOpen(false), [])

  const logout = useCallback(() => {
    clearTokens()
    setUser(null)
  }, [])

  // 启动引导：有 access token 就拉取 /me 还原登录态；并注册全局 401 回调。
  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true

    setUnauthorizedHandler(() => {
      setUser(null)
      openAuth('login')
    })

    void (async () => {
      if (getAccessToken()) {
        try {
          const res = await getMe()
          if (res.success && res.data) setUser(res.data)
        } catch {
          /* 令牌失效已由拦截器清理 */
        }
      }
      setReady(true)
    })()

    return () => setUnauthorizedHandler(null)
  }, [openAuth])

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginUser({ email, password })
    if (!res.success || !res.data) throw new Error(res.error || 'login failed')
    setTokens(res.data.access_token, res.data.refresh_token)
    setUser(res.data.user)
    setDialogOpen(false)
  }, [])

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    const res = await registerUser({ email, password, display_name: displayName })
    if (!res.success || !res.data) throw new Error(res.error || 'register failed')
    setTokens(res.data.access_token, res.data.refresh_token)
    setUser(res.data.user)
    setDialogOpen(false)
  }, [])

  // 重新拉取 /me（验证邮箱后刷新 email_verified 等状态）
  const refreshUser = useCallback(async () => {
    const res = await getMe()
    if (res.success && res.data) setUser(res.data)
  }, [])

  const resendVerification = useCallback(async () => {
    const res = await apiResendVerification()
    if (!res.success) throw new Error(res.error || 'resend failed')
    return res.data?.message || ''
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      ready,
      isAuthenticated: !!user,
      dialogOpen,
      dialogMode,
      openAuth,
      closeAuth,
      setDialogMode,
      login,
      register,
      logout,
      refreshUser,
      resendVerification,
    }),
    [
      user,
      ready,
      dialogOpen,
      dialogMode,
      openAuth,
      closeAuth,
      login,
      register,
      logout,
      refreshUser,
      resendVerification,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 <AuthProvider> 内使用')
  return ctx
}
