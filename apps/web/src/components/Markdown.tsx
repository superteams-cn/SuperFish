import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { cn } from '@/lib/utils'

interface MarkdownProps {
  content: string
  className?: string
  /** 去掉开头的二级标题（章节标题已在外层显示） */
  stripLeadingH2?: boolean
}

/** 统一的 Markdown 渲染组件（GFM + Tailwind 排版样式）。 */
export function Markdown({ content, className, stripLeadingH2 }: MarkdownProps) {
  const text = stripLeadingH2 ? content.replace(/^##\s+.+\n+/, '') : content
  return (
    <div
      className={cn(
        'prose prose-sm text-foreground max-w-none',
        'prose-headings:font-semibold prose-headings:text-foreground',
        // typography 插件默认把 <strong> 设为 gray-900，深色下近黑看不见；
        // 报告小标题都转成了 **粗体**，故必须显式跟随 foreground
        'prose-strong:text-foreground prose-p:leading-relaxed prose-li:my-0.5',
        'prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-[0.85em] prose-code:before:content-none prose-code:after:content-none',
        'prose-pre:bg-muted prose-pre:text-foreground',
        'prose-blockquote:border-l-brand prose-blockquote:text-muted-foreground',
        'prose-a:text-brand',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}
