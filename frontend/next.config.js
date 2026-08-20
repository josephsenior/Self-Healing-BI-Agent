/** @type {import('next').NextConfig} */
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_HTTP_URL || 'http://127.0.0.1:8000';

const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: '/static/:path*',
        destination: `${backendUrl}/static/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
