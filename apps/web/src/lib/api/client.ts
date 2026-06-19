import axios from 'axios'
import i18n from '@/i18n'

// 创建 axios 实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000, // 5 分钟超时（本体生成可能需要较长时间）
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：附带当前语言
service.interceptors.request.use(
  (config) => {
    config.headers['Accept-Language'] = i18n.language
    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  },
)

// 响应拦截器：解包 data 并对 success=false 抛错
service.interceptors.response.use(
  (response) => {
    const res = response.data
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    return res
  },
  (error) => {
    console.error('Response error:', error)
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }
    return Promise.reject(error)
  },
)

/** 带指数退避重试的请求包装。 */
export async function requestWithRetry<T>(
  requestFn: () => Promise<T>,
  maxRetries = 3,
  delay = 1000,
): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error
      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise((resolve) => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
  // 理论上不可达
  throw new Error('requestWithRetry: unreachable')
}

export default service
