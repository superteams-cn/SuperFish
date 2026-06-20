/**
 * 全屏流动光晕背景。玻璃质感面板（.glass）依赖其下方有彩色内容透上来，
 * 因此玻璃化的页面在最底层渲染这个组件（fixed, -z-10）。
 */
export function AuroraBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-[#eef1f9] dark:bg-[#070a12]"
    >
      <div className="absolute -left-40 -top-40 h-[44rem] w-[44rem] animate-[blob-float_19s_ease-in-out_infinite] rounded-full bg-indigo-400/45 blur-[130px] dark:bg-indigo-600/30" />
      <div className="absolute -right-32 top-1/4 h-[40rem] w-[40rem] animate-[blob-float_24s_ease-in-out_infinite_reverse] rounded-full bg-fuchsia-400/40 blur-[130px] dark:bg-fuchsia-700/25" />
      <div className="absolute -bottom-48 left-1/4 h-[42rem] w-[42rem] animate-[blob-float_21s_ease-in-out_infinite] rounded-full bg-sky-300/45 blur-[130px] dark:bg-sky-600/25" />
      <div className="absolute right-1/4 top-2/3 h-[28rem] w-[28rem] animate-[blob-float_26s_ease-in-out_infinite_reverse] rounded-full bg-violet-300/35 blur-[120px] dark:bg-violet-700/20" />
    </div>
  )
}
