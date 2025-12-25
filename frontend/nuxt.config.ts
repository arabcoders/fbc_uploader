import tailwindcss from "@tailwindcss/vite";
import path from "path";

let extraNitro = {}
try {
  const API_URL = process.env.NUXT_API_URL;
  if (API_URL) {
    extraNitro = {
      devProxy: {
        '/api/': {
          target: API_URL,
          changeOrigin: true
        }
      }
    }
  }
}
catch { }

export default defineNuxtConfig({
  ssr: false,
  devtools: { enabled: false },
  devServer: {
    port: 8082,
    host: "0.0.0.0",
  },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      APP_ENV: process.env.NODE_ENV,
    }
  },
  build: {
    transpile: [],
  },
  app: {
    baseURL: '/',
    buildAssetsDir: "assets",
    head: {
      "meta": [
        { "charset": "utf-8" },
        { "name": "viewport", "content": "width=device-width, initial-scale=1.0, maximum-scale=1.0" },
        { "name": "theme-color", "content": "#000000" },
      ],
      base: { "href": "/" },
      link: []
    },
    pageTransition: { name: 'page', mode: 'out-in' }
  },
  router: {
    options: {
      linkActiveClass: "is-selected",
    }
  },

  modules: [
    '@pinia/nuxt',
    '@vueuse/nuxt',
    '@nuxt/ui',
    'development' === process.env.NODE_ENV ? '@nuxt/eslint' : '',
  ].filter(Boolean),

  nitro: {
    output: {
      publicDir: path.join(__dirname, 'production' === process.env.NODE_ENV ? 'exported' : 'dist')
    },
    ...extraNitro,
  },
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: true,
    },
    build: {
      chunkSizeWarningLimit: 2000,
    }
  },
  postcss: {
    plugins: {
      "@tailwindcss/postcss": {},
      autoprefixer: {},
    },
  },
  telemetry: false,
  compatibilityDate: "2025-08-03",
})
