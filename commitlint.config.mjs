// 约定式提交校验。允许中文 subject，放宽长度限制以适配中文描述。
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'subject-case': [0],
    'subject-max-length': [2, 'always', 100],
    'body-max-line-length': [0],
  },
}
