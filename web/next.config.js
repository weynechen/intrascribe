/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // Enable Docker deployment
  
  // 环境配置 - 支持开发、生产和Docker环境的无感知切换
  async rewrites() {
    const isDev = process.env.NODE_ENV === 'development'
    const isDocker = process.env.DOCKER_ENV === 'true'
    const isProd = process.env.NODE_ENV === 'production'
    
    console.log('🔧 Next.js环境配置:', {
      NODE_ENV: process.env.NODE_ENV,
      DOCKER_ENV: process.env.DOCKER_ENV,
      isDev,
      isDocker,
      isProd
    })
    
    // 根据环境确定后端和Supabase地址
    let backendUrl, supabaseUrl
    
    if (isDocker) {
      // Docker环境：使用内部服务名
      backendUrl = 'http://api-service:8000'
      supabaseUrl = 'http://host.docker.internal:54321'
    } else if (isDev) {
      // 开发环境：使用本地地址
      backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
      supabaseUrl = process.env.SUPABASE_URL || 'http://localhost:54321'
    } else if (isProd) {
      // 生产环境：优先使用环境变量，无代理时不启用
      const useProxy = process.env.NEXT_PUBLIC_USE_PROXY === 'true'
      
      if (useProxy) {
        // 生产环境使用代理（适用于Nginx等场景）
        backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_SERVER_URL
        supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL
      }
      
      console.log('🏭 生产环境代理配置:', {
        useProxy,
        backendUrl,
        supabaseUrl,
        NEXT_PUBLIC_USE_PROXY: process.env.NEXT_PUBLIC_USE_PROXY
      })
    }
    
    // 只在需要代理的环境下启用rewrite规则
    if ((isDev || isDocker) || (isProd && process.env.NEXT_PUBLIC_USE_PROXY === 'true')) {
      console.log('✅ 启用代理规则:', { backendUrl, supabaseUrl })
      
      return [
        // Backend API proxy
        {
          source: '/api/:path*',
          destination: `${backendUrl}/api/:path*`,
        },
        // WebRTC endpoints
        {
          source: '/webrtc/:path*',
          destination: `${backendUrl}/webrtc/:path*`,
        },
        // Direct backend endpoints
        {
          source: '/send_input',
          destination: `${backendUrl}/send_input`,
        },
        {
          source: '/transcript',
          destination: `${backendUrl}/transcript`,
        },
        // Supabase proxy (如果配置了supabaseUrl)
        ...(supabaseUrl ? [
          {
            source: '/supabase/:path*',
            destination: `${supabaseUrl}/:path*`,
          },
          {
            source: '/storage/:path*',
            destination: `${supabaseUrl}/storage/:path*`,
          }
        ] : [])
      ]
    }
    
    console.log('🚫 不启用代理规则')
    return []
  },

  // CORS配置 - 仅在开发和Docker环境启用
  async headers() {
    const isDev = process.env.NODE_ENV === 'development'
    const isDocker = process.env.DOCKER_ENV === 'true'
    
    // 只在开发环境和Docker环境启用CORS头
    // 生产环境应该通过Nginx或后端服务处理CORS
    if (isDev || isDocker) {
      console.log('✅ 启用CORS头')
      return [
        {
          source: '/api/:path*',
          headers: [
            { key: 'Access-Control-Allow-Origin', value: '*' },
            { key: 'Access-Control-Allow-Methods', value: 'GET, POST, PUT, DELETE, OPTIONS' },
            { key: 'Access-Control-Allow-Headers', value: 'Content-Type, Authorization' },
          ],
        },
        // 为storage请求添加CORS头
        {
          source: '/storage/:path*',
          headers: [
            { key: 'Access-Control-Allow-Origin', value: '*' },
            { key: 'Access-Control-Allow-Methods', value: 'GET, HEAD, OPTIONS' },
            { key: 'Access-Control-Allow-Headers', value: 'Range, Accept-Encoding' },
          ],
        },
      ]
    }
    
    console.log('🚫 不启用CORS头（生产环境）')
    return []
  },
  
  // 环境变量配置验证
  async generateBuildId() {
    const buildId = `build-${Date.now()}`
    
    // 在构建时验证必要的环境变量
    const requiredEnvVars = [
      'NEXT_PUBLIC_SUPABASE_ANON_KEY'
    ]
    
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName])
    
    if (missingVars.length > 0) {
      console.warn('⚠️ 缺少必要的环境变量:', missingVars)
      console.warn('请检查您的环境配置文件（.env.development, .env.production, .env.local）')
    }
    
    // 生产环境额外检查
    if (process.env.NODE_ENV === 'production') {
      const prodRequiredVars = [
        'NEXT_PUBLIC_SUPABASE_URL',
        'NEXT_PUBLIC_API_SERVER_URL'
      ]
      
      const missingProdVars = prodRequiredVars.filter(varName => 
        !process.env[varName] && process.env.NEXT_PUBLIC_USE_PROXY !== 'true'
      )
      
      if (missingProdVars.length > 0 && process.env.NEXT_PUBLIC_USE_PROXY !== 'true') {
        console.warn('⚠️ 生产环境缺少API地址配置:', missingProdVars)
        console.warn('如需使用代理，请设置 NEXT_PUBLIC_USE_PROXY=true')
      }
    }
    
    return buildId
  }
}

module.exports = nextConfig 