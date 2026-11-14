// Copies Cesium's runtime assets (workers, widgets css, textures) into public/cesium so Vite can serve them.
import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
const src = resolve('node_modules/cesium/Build/Cesium')
const dst = resolve('public/cesium')
if (!existsSync(src)) { console.error('cesium not installed; run npm install'); process.exit(1) }
mkdirSync(dst, { recursive: true })
for (const d of ['Workers', 'ThirdParty', 'Assets', 'Widgets']) cpSync(`${src}/${d}`, `${dst}/${d}`, { recursive: true })
console.log('Cesium assets copied to public/cesium')
