import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icons.svg'],
      manifest: {
        name: 'Job Search Automation',
        short_name: 'Jobs',
        description: 'Recherche d\'emploi automatisée : offres, candidatures et suivi.',
        theme_color: '#f4f5fa',
        background_color: '#f4f5fa',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Ne jamais mettre en cache /api ni /data : statuts et recherches doivent rester frais.
        navigateFallbackDenylist: [/^\/api/, /^\/data/],
        globIgnores: ['**/data/**'],
        runtimeCaching: [
          {
            urlPattern: /^\/api\//,
            handler: 'NetworkOnly',
          },
          {
            urlPattern: /^\/data\//,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
  server: {
    // Proxy : les requêtes /api sont redirigées vers le backend Node.
    // Le port 3001 est souvent pris par un autre projet ; dans ce cas le proxy
    // répond du HTML au lieu du JSON et le front croit le backend absent.
    // VITE_API_PORT doit valoir le PORT passé à `node server/index.js`.
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.VITE_API_PORT || 3001}`,
        changeOrigin: true,
      },
    },
  },
})
