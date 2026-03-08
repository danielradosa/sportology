// Injected at build time by Vite (see vite.config.ts)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const __APP_VERSION__: any

export const APP_VERSION: string = String(__APP_VERSION__ || '')
