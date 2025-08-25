/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  
  // 开发环境配置
  async rewrites() {
    // 只在开发环境下启用代理（本地开发无需依赖 nginx）
    if (process.env.NODE_ENV === 'development') {
      return [
        // Backend API proxy
        {
          source: '/api/:path*',
          destination: 'http://localhost:8000/api/:path*',
        },
        // WebRTC endpoints
        {
          source: '/webrtc/:path*',
          destination: 'http://localhost:8000/webrtc/:path*',
        },
        // Direct backend endpoints
        {
          source: '/send_input',
          destination: 'http://localhost:8000/send_input',
        },
        {
          source: '/transcript',
          destination: 'http://localhost:8000/transcript',
        },
        // Supabase proxy
        {
          source: '/supabase/:path*',
          destination: 'http://localhost:54321/:path*',
        },
        // Storage proxy
        {
          source: '/storage/:path*',
          destination: 'http://localhost:54321/storage/:path*',
        },
      ]
    }
    return []
  },

  // 开发环境下的CORS配置
  async headers() {
    if (process.env.NODE_ENV === 'development') {
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