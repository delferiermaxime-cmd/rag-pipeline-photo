/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Pas de rewrites — nginx est le seul proxy entre le browser et le backend.
  // NEXT_PUBLIC_API_URL="" + nginx → backend est l'architecture correcte.
}

module.exports = nextConfig
