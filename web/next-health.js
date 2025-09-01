// Simple health check endpoint for Docker
const http = require('http')

const healthCheck = http.createServer((req, res) => {
  if (req.url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }))
  } else {
    res.writeHead(404)
    res.end('Not Found')
  }
})

healthCheck.listen(3001, () => {
  console.log('Health check server running on port 3001')
})
