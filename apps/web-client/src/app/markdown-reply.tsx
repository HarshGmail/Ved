import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./chat.module.css";

const REMARK_PLUGINS = [remarkGfm];

const COMPONENTS: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className={styles.tableScroll}>
      <table>{children}</table>
    </div>
  ),
};

export function MarkdownReply({ text }: { text: string }) {
  return (
    <div className={styles.markdown}>
      <Markdown remarkPlugins={REMARK_PLUGINS} components={COMPONENTS}>
        {text}
      </Markdown>
    </div>
  );
}
