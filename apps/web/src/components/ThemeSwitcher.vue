<template>
  <div class="theme-switcher" ref="switcherRef">
    <button class="switcher-trigger" :title="$t('theme.label')" @click="open = !open">
      <component :is="iconFor(theme)" />
      <span class="switcher-current">{{ $t('theme.' + theme) }}</span>
      <span class="caret">{{ open ? '▲' : '▼' }}</span>
    </button>
    <ul v-if="open" class="switcher-dropdown">
      <li
        v-for="t in themes"
        :key="t"
        class="switcher-option"
        :class="{ active: t === theme }"
        @click="choose(t)"
      >
        <component :is="iconFor(t)" />
        <span>{{ $t('theme.' + t) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, h, onMounted, onUnmounted } from 'vue'
import { useTheme } from '@/store/theme.js'

const { theme, themes, setTheme } = useTheme()
const open = ref(false)
const switcherRef = ref(null)

// 每个主题对应的几何/象征图标（统一 16x16）
const svg = (children) =>
  h('svg', { viewBox: '0 0 24 24', width: 16, height: 16, fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, children)

const icons = {
  // 太阳
  light: () => svg([
    h('circle', { cx: 12, cy: 12, r: 5 }),
    h('line', { x1: 12, y1: 1, x2: 12, y2: 3 }), h('line', { x1: 12, y1: 21, x2: 12, y2: 23 }),
    h('line', { x1: 4.22, y1: 4.22, x2: 5.64, y2: 5.64 }), h('line', { x1: 18.36, y1: 18.36, x2: 19.78, y2: 19.78 }),
    h('line', { x1: 1, y1: 12, x2: 3, y2: 12 }), h('line', { x1: 21, y1: 12, x2: 23, y2: 12 }),
    h('line', { x1: 4.22, y1: 19.78, x2: 5.64, y2: 18.36 }), h('line', { x1: 18.36, y1: 5.64, x2: 19.78, y2: 4.22 })
  ]),
  // 月亮
  dark: () => svg([h('path', { d: 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z' })]),
  // 包豪斯：圆 + 方 + 三角
  bauhaus: () => svg([
    h('circle', { cx: 6, cy: 8, r: 3.2 }),
    h('rect', { x: 13, y: 4.8, width: 6.5, height: 6.5 }),
    h('path', { d: 'M12 14 L17 21 L7 21 Z' })
  ]),
  // 多巴胺：星星 + 闪光
  dopamine: () => svg([
    h('path', { d: 'M12 2.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 15.8 6.8 18.6l1-5.8-4.3-4.1 5.9-.9L12 2.5z' }),
    h('path', { d: 'M20 3v4' }),
    h('path', { d: 'M18 5h4' })
  ]),
  // 数字黄金暗域：金币与精密刻线
  digitalGold: () => svg([
    h('circle', { cx: 12, cy: 12, r: 8.5 }),
    h('path', { d: 'M10 7h3.2a2.1 2.1 0 0 1 0 4.2H10z' }),
    h('path', { d: 'M10 11.2h3.8a2.4 2.4 0 0 1 0 4.8H10z' }),
    h('path', { d: 'M10 7v10' }),
    h('path', { d: 'M8.5 7h2' }),
    h('path', { d: 'M8.5 17h2' }),
    h('path', { d: 'M11.5 5.5v2' }),
    h('path', { d: 'M13.5 5.5v2' }),
    h('path', { d: 'M11.5 16.5v2' }),
    h('path', { d: 'M13.5 16.5v2' })
  ])
}
const iconFor = (t) => icons[t] || icons.light

const choose = (t) => { setTheme(t); open.value = false }

const onClickOutside = (e) => {
  if (switcherRef.value && !switcherRef.value.contains(e.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.theme-switcher {
  position: relative;
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
}

.switcher-trigger {
  background: transparent;
  color: #333;
  border: 1px solid #CCC;
  padding: 4px 10px;
  font-family: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: border-color 0.2s, color 0.2s;
}

.switcher-trigger:hover {
  border-color: #999;
  color: #000;
}

.switcher-current {
  line-height: 1;
}

.caret {
  font-size: 0.55rem;
}

.switcher-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: #FFFFFF;
  border: 1px solid #DDD;
  list-style: none;
  padding: 4px 0;
  min-width: 100%;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.switcher-option {
  padding: 6px 12px;
  font-size: 0.8rem;
  color: #333;
  cursor: pointer;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
}

.switcher-option:hover {
  background: #F0F0F0;
}

.switcher-option.active {
  color: #D02020;
  font-weight: 700;
}
</style>
