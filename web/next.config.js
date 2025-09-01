/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // Enable Docker deployment
  
  // 环境配置 - 支持开发和生产环境
  async rewrites() {
    const isDev = process.env.NODE_ENV === 'development'
    const isDocker = process.env.DOCKER_ENV === 'true'
    
    // 根据环境确定后端和Supabase地址
    const backendUrl = isDocker ? 'http://api-service:8000' : 
                      isDev ? 'http://localhost:8000' : 
                      process.env.BACKEND_URL || 'http://localhost:8000'
    
    const supabaseUrl = isDocker ? 'http://host.docker.internal:54321' :
                       'http://localhost:54321'
    
    if (isDev || isDocker) {
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
        // Supabase proxy
        {
          source: '/supabase/:path*',
          destination: `${supabaseUrl}/:path*`,
        },
        // Storage proxy
        {
          source: '/storage/:path*',
          destination: `${supabaseUrl}/storage/:path*`,
        },
      ]
    }
    return []
  },

  // CORS配置 - 支持开发和Docker环境
  async headers() {
    const isDev = process.env.NODE_ENV === 'development'
    const isDocker = process.env.DOCKER_ENV === 'true'
    
    if (isDev || isDocker) {
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
    return []
  },
}

module.exports = nextConfig 