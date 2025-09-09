/**
 * Unified API client for Supabase and API Server
 */

// Environment configuration interface
interface ApiConfig {
  supabaseUrl: string
  apiServerUrl: string
  environment: 'development' | 'production' | 'docker'
}

// Request options interface
interface RequestOptions extends RequestInit {
  timeout?: number
  skipAuth?: boolean
}

// API Response types
interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

// Error class for API errors
class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public response?: Response
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Get API configuration
 */
function getApiConfig(): ApiConfig {
  const isClient = typeof window !== 'undefined'
  const environment = process.env.NODE_ENV === 'production' ? 'production' : 
                     process.env.DOCKER_ENV === 'true' ? 'docker' : 'development'

  // Client-side configuration
  if (isClient) {
    const origin = window.location.origin
    
    if (environment === 'development') {
      return {
        supabaseUrl: `${origin}/supabase`, // Use Next.js proxy
        apiServerUrl: '/api', // Use Next.js proxy
        environment: 'development'
      }
    } else {
      // Production - use environment variables with fallbacks
      return {
        supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL || `${origin}/supabase`,
        apiServerUrl: process.env.NEXT_PUBLIC_API_SERVER_URL || '/api',
        environment: 'production'
      }
    }
  }

  // Server-side configuration  
  if (environment === 'docker') {
    return {
      supabaseUrl: 'http://host.docker.internal:54321',
      apiServerUrl: 'http://api-service:8000/api',
      environment: 'docker'
    }
  } else if (environment === 'production') {
    return {
      supabaseUrl: process.env.SUPABASE_URL || 'http://localhost:54321',
      apiServerUrl: process.env.API_SERVER_URL || 'http://localhost:8000/api',
      environment: 'production'
    }
  } else {
    // Development server-side
    return {
      supabaseUrl: 'http://localhost:54321',
      apiServerUrl: 'http://localhost:8000/api',
      environment: 'development'
    }
  }
}

/**
 * Unified HTTP client
 */
class HttpClient {
  private config: ApiConfig
  private getAuthToken: (() => string | null) | null = null

  constructor() {
    this.config = getApiConfig()
  }

  /**
   * Set authentication token getter
   */
  setAuthTokenGetter(getter: () => string | null) {
    this.getAuthToken = getter
  }

  /**
   * Make HTTP request with unified error handling
   */
  private async request<T>(
    url: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { timeout = 30000, skipAuth = false, ...fetchOptions } = options

    // Setup headers
    const headers: Record<string, string> = {
      ...fetchOptions.headers as Record<string, string>
    }

    // Only set Content-Type if not already specified and body is not FormData
    if (!headers['Content-Type'] && !headers['content-type']) {
      const isFormData = fetchOptions.body instanceof FormData
      if (!isFormData) {
        headers['Content-Type'] = 'application/json'
      }
      // For FormData, let the browser set the correct Content-Type with boundary
    }

    // Add authentication if available and not skipped
    if (!skipAuth && this.getAuthToken) {
      const token = this.getAuthToken()
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
    }

    // Setup request config
    const config: RequestInit = {
      ...fetchOptions,
      headers
    }

    // Add timeout support
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)
    config.signal = controller.signal

    try {
      const response = await fetch(url, config)
      clearTimeout(timeoutId)

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error')
        throw new ApiError(
          `HTTP ${response.status}: ${errorText}`,
          response.status,
          response
        )
      }

      // Handle different content types
      const contentType = response.headers.get('content-type')
      if (contentType?.includes('application/json')) {
        return await response.json()
      } else {
        return await response.text() as unknown as T
      }

    } catch (error) {
      clearTimeout(timeoutId)
      
      if (error instanceof ApiError) {
        throw error
      }
      
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new ApiError('Request timeout')
        }
        throw new ApiError(`Network error: ${error.message}`)
      }
      
      throw new ApiError('Unknown error occurred')
    }
  }

  /**
   * Make request to Supabase
   */
  async supabase<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const url = `${this.config.supabaseUrl}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`
    return this.request<T>(url, options)
  }

  /**
   * Make request to API Server
   */
  async apiServer<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const url = `${this.config.apiServerUrl}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`
    return this.request<T>(url, options)
  }

  /**
   * GET request
   */
  async get<T>(backend: 'supabase' | 'api', endpoint: string, options: RequestOptions = {}): Promise<T> {
    const requestOptions = { ...options, method: 'GET' }
    return backend === 'supabase' 
      ? this.supabase<T>(endpoint, requestOptions)
      : this.apiServer<T>(endpoint, requestOptions)
  }

  /**
   * POST request
   */
  async post<T>(
    backend: 'supabase' | 'api',
    endpoint: string,
    data?: unknown,
    options: RequestOptions = {}
  ): Promise<T> {
    const requestOptions = {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined
    }
    return backend === 'supabase'
      ? this.supabase<T>(endpoint, requestOptions)
      : this.apiServer<T>(endpoint, requestOptions)
  }

  /**
   * PUT request
   */
  async put<T>(
    backend: 'supabase' | 'api',
    endpoint: string,
    data?: unknown,
    options: RequestOptions = {}
  ): Promise<T> {
    const requestOptions = {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined
    }
    return backend === 'supabase'
      ? this.supabase<T>(endpoint, requestOptions)
      : this.apiServer<T>(endpoint, requestOptions)
  }

  /**
   * DELETE request
   */
  async delete<T>(
    backend: 'supabase' | 'api',
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const requestOptions = { ...options, method: 'DELETE' }
    return backend === 'supabase'
      ? this.supabase<T>(endpoint, requestOptions)
      : this.apiServer<T>(endpoint, requestOptions)
  }

  /**
   * Get current configuration
   */
  getConfig(): ApiConfig {
    return { ...this.config }
  }

  /**
   * Update configuration (mainly for testing)
   */
  updateConfig(newConfig: Partial<ApiConfig>) {
    this.config = { ...this.config, ...newConfig }
  }
}

// Create and export singleton instance
export const httpClient = new HttpClient()

// Export types and classes
export type { ApiConfig, RequestOptions, ApiResponse }
export { ApiError, HttpClient }

// Convenience functions
export const apiGet = <T>(backend: 'supabase' | 'api', endpoint: string, options?: RequestOptions) =>
  httpClient.get<T>(backend, endpoint, options)

export const apiPost = <T>(backend: 'supabase' | 'api', endpoint: string, data?: unknown, options?: RequestOptions) =>
  httpClient.post<T>(backend, endpoint, data, options)

export const apiPut = <T>(backend: 'supabase' | 'api', endpoint: string, data?: unknown, options?: RequestOptions) =>
  httpClient.put<T>(backend, endpoint, data, options)

export const apiDelete = <T>(backend: 'supabase' | 'api', endpoint: string, options?: RequestOptions) =>
  httpClient.delete<T>(backend, endpoint, options)
