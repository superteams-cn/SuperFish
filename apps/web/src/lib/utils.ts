import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** 合并 Tailwind 类名，自动处理冲突（shadcn/ui 约定）。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
