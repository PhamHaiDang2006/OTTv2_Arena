import { useMemo, type ReactNode } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-c';
import 'prismjs/components/prism-cpp';
import 'prismjs/components/prism-java';
function nodes(tokens: (string | Prism.Token)[]): ReactNode {
  return tokens.map((token, index) =>
    typeof token === 'string' ? (
      token
    ) : (
      <span className={`token ${token.type}`} key={index}>
        {typeof token.content === 'string'
          ? token.content
          : nodes(Array.isArray(token.content) ? token.content : [token.content])}
      </span>
    ),
  );
}
export function SourceCode({ content, path }: { content: string; path: string }) {
  const language = path.endsWith('.py')
    ? 'python'
    : /\.(cpp|cc|hpp|h)$/.test(path)
      ? 'cpp'
      : path.endsWith('.java')
        ? 'java'
        : path.endsWith('.js')
          ? 'javascript'
          : '';
  const output = useMemo(
    () =>
      language && Prism.languages[language]
        ? nodes(Prism.tokenize(content, Prism.languages[language]))
        : content,
    [language, content],
  );
  return (
    <pre>
      <code>{output}</code>
    </pre>
  );
}
