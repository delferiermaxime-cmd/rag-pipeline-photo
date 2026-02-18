/** @type {import('next').NextConfig} */
const nextConfig = {
  // CRITIQUE : génère .next/standalone/ utilisé par le Dockerfile
  // Sans cette ligne, node server.js n'existe pas et le conteneur plante
  output: 'standalone',

  // FIX : ne pas exposer la version de Next.js dans les headers HTTP
  poweredByHeader: false,

  // Prêt pour les images externes si besoin dans le futur
  // images: {
  //   remotePatterns: [
  //     { protocol: 'https', hostname: 'example.com' },
  //   ],
  // },

  // Pas de rewrites ici — Nginx est le seul proxy entre le browser et le backend
  // NEXT_PUBLIC_API_URL="" + nginx → /api/* est redirigé vers backend:8000
}

module.exports = nextConfig
