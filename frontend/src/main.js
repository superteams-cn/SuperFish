import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { initTheme } from './store/theme.js'
import './assets/themes/bauhaus.css'
import './assets/themes/dopamine.css'
import './assets/themes/digital-gold.css'

// 在挂载前应用已保存的主题，避免首屏闪烁
initTheme()

const app = createApp(App)

app.use(router)
app.use(i18n)

app.mount('#app')
