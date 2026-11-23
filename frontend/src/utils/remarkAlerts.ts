import type { Blockquote, Root, RootContent } from 'mdast';

export const ALERT_TYPES = ['note', 'tip', 'important', 'warning', 'caution'] as const;
export type AlertType = (typeof ALERT_TYPES)[number];

const MARKER = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*\n?/i;

function markAlert(quote: Blockquote) {
  const first = quote.children[0];
  if (first?.type !== 'paragraph') return;
  const text = first.children[0];
  if (text?.type !== 'text') return;
  const match = MARKER.exec(text.value);
  if (!match) return;
  text.value = text.value.slice(match[0].length);
  if (!text.value) first.children.shift();
  if (first.children[0]?.type === 'break') first.children.shift();
  if (first.children.length === 0) quote.children.shift();
  quote.data = { ...quote.data, hProperties: { dataAlert: match[1]!.toLowerCase() } };
}

function walk(nodes: RootContent[]) {
  for (const node of nodes) {
    if (node.type === 'blockquote') markAlert(node);
    if ('children' in node) walk(node.children as RootContent[]);
  }
}

// GitHub alerts (`> [!NOTE]`): marks the blockquote with data-alert for the renderer.
export default function remarkAlerts() {
  return (tree: Root) => walk(tree.children);
}
