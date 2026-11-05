import ReactMarkdown, { type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

// Untrusted answers may describe images, but must never initiate image requests.
// Keep this policy outside individual surfaces, including public receipts.
type SafeMarkdownProps = Pick<Options, "children" | "allowedElements" | "unwrapDisallowed"> & {
  components?: Omit<NonNullable<Options["components"]>, "img">;
};

export default function SafeMarkdown({ components, ...props }: SafeMarkdownProps) {
  return <ReactMarkdown {...props} skipHtml remarkPlugins={[remarkGfm]} components={{
    ...components,
    img: ({ alt }) => <>{alt}</>,
  }} />;
}
