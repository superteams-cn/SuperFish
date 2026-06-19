<template>
  <router-view />
</template>

<script setup>
// 使用 Vue Router 来管理页面
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* ===== 明暗主题 =====
   该应用的颜色大量硬编码在各组件的 scoped 样式中，
   因此暗色模式采用根节点反相方案：翻转明度、保留色相，
   再对位图（如 logo）反向反相以保持原貌。 */
html[data-theme="dark"] {
  filter: invert(1) hue-rotate(180deg);
  background-color: #ffffff; /* 反相后即为黑色背景 */
}

/* 位图 / 需要保持原色的元素：二次反相抵消 */
html[data-theme="dark"] img,
html[data-theme="dark"] video,
html[data-theme="dark"] .no-invert {
  filter: invert(1) hue-rotate(180deg);
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #000000;
  background-color: #ffffff;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: #000000;
}

::-webkit-scrollbar-thumb:hover {
  background: #333333;
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}
</style>
