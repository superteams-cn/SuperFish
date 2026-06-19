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
        'prose prose-sm max-w-none text-foreground',
        'prose-headings:font-semibold prose-headings:text-foreground',
        'prose-p:leading-relaxed prose-li:my-0.5',
        'prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-[0.85em] prose-code:before:content-none prose-code:after:content-none',
        'prose-pre:bg-muted prose-pre:text-foreground',
        'prose-blockquote:border-l-[#FF5722] prose-blockquote:text-muted-foreground',
        'prose-a:text-[#FF5722]',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}
