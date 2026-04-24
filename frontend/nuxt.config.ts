import { defineNuxtConfig } from 'nuxt/config';

let extraNitro = {}
const isProd = 'production' === process.env.NODE_ENV
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
  sourcemap: false === isProd,
  devtools: { enabled: false === isProd },
  devServer: {
    port: 8082,
    host: "0.0.0.0",
  },
  css: ['~/assets/css/tailwind.css'],
  runtimeConfig: {
    public: {
      APP_ENV: process.env.NODE_ENV,
    }
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
    '@vueuse/nuxt',
    '@nuxt/ui',
    '@nuxt/eslint',
  ],
  icon: {
    provider: 'none',
    fallbackToApi: false,
    clientBundle: {
      scan: {
        globInclude: ['app/**/*.{vue,ts,js}', 'node_modules/@nuxt/ui/dist/shared/ui*.mjs'],
        globExclude: ['dist', 'build', 'coverage', 'test', 'tests', '.*'],
      },
    },
  },
  nitro: {
    sourceMap: false === isProd,
    output: {
      publicDir: isProd ? __dirname + '/exported' : __dirname + '/dist',
    },
    ...extraNitro,
  },
  vite: {
    server: {
      allowedHosts: true,
    },
    build: {
      chunkSizeWarningLimit: 2000,
    },
    optimizeDeps: {
      include: [
        '@vue/devtools-core',
        '@vue/devtools-kit',
        'marked',
        'marked-base-url',
        'marked-alert',
        'marked-gfm-heading-id',
        'tus-js-client',
      ]
    }
  },
  telemetry: false,
  compatibilityDate: "2025-08-03",
})
