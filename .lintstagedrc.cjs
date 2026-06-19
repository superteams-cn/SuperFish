const path = require('path')

// monorepo 下 lint-staged 从仓库根运行；eslint 需在 apps/web 内执行才能找到 flat config，
// 故 cd 进 apps/web 并用相对路径调用。prettier/ruff 可直接用绝对路径。
module.exports = {
  'apps/web/**/*.{ts,tsx}': (files) => {
    const rel = files.map((f) => path.relative('apps/web', f)).join(' ')
    const abs = files.join(' ')
    return [`bash -c "cd apps/web && eslint --fix ${rel}"`, `prettier --write ${abs}`]
  },
  'apps/web/**/*.{js,json,css}': (files) => [`prettier --write ${files.join(' ')}`],
  'apps/api/**/*.py': (files) => {
    const abs = files.join(' ')
    return [
      `uv run --project apps/api ruff check --fix ${abs}`,
      `uv run --project apps/api ruff format ${abs}`,
    ]
  },
}
