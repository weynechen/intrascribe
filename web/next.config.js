/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', 
  devIndicators: false,
  async rewrites() {
    
    let backendUrl, supabaseUrl
  const environment = process.env.NODE_ENV === 'production' ? 'production' : 
                     process.env.DOCKER_ENV === 'true' ? 'docker' : 'development'
    if (environment === 'development') {
    backendUrl = process.env.NEXT_PUBLIC_API_SERVER_URL || 'http://localhost:8000'
    supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'http://localhost:54321'
      
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
    return []
  },

  async headers() {
    
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, POST, PUT, DELETE, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Content-Type, Authorization' },
        ],
      },
      {
        source: '/storage/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, HEAD, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Range, Accept-Encoding' },
        ],
      },
    ]
    
  },
  
  async generateBuildId() {
    const buildId = `build-${Date.now()}`
    
    const requiredEnvVars = [
      'NEXT_PUBLIC_SUPABASE_ANON_KEY'
    ]
    
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName])
    
    if (missingVars.length > 0) {
      console.warn('missing env vars:', missingVars)
    }
    
    
    return buildId
  }
}

module.exports = nextConfig 