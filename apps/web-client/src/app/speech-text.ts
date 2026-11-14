const MAX_CHUNK_LENGTH = 200;
const CODE_BLOCK = /```[\s\S]*?(?:```|$)/g;
const CODE_BLOCK_REPLACEMENT = "\ncode omitted.\n";
const HORIZONTAL_RULE = /^[ \t]*(?:[-*_][ \t]*){3,}$/gm;
const TABLE_DIVIDER = /^[ \t]*\|?[ \t]*:?-{3,}:?(?:[ \t]*\|[ \t]*:?-{3,}:?)*[ \t]*\|?[ \t]*$/gm;
const TABLE_ROW = /^[ \t]*\|(.*)\|[ \t]*$/gm;
const INLINE_CODE = /`([^`]*)`/g;
const IMAGE_OR_LINK = /!?\[([^\]]*)\]\([^)]*\)/g;
const AUTOLINK = /<https?:\/\/[^>]*>/g;
const BARE_URL = /https?:\/\/\S+/g;
const HTML_TAG = /<\/?[a-zA-Z][^>]*>/g;
const HEADING = /^[ \t]{0,3}#{1,6}[ \t]+/gm;
const BLOCKQUOTE = /^[ \t]*>[ \t]?/gm;
const LIST_MARKER = /^[ \t]*(?:[-*+]|\d+[.)])[ \t]+/gm;
const BOLD = /\*\*(.+?)\*\*|__(.+?)__/g;
const STRIKETHROUGH = /~~(.+?)~~/g;
const ITALIC_STARS = /\*([^*\n]+)\*/g;
const ITALIC_UNDERSCORES = /(^|[\s(])_([^_\n]+)_(?=[\s).,!?]|$)/g;
const EMOJI = /[\p{Extended_Pictographic}\p{Regional_Indicator}\u200D\uFE0F\u20E3]/gu;
const SPACE_BEFORE_PUNCTUATION = /[ \t]+([.,!?;:])/g;
const ENDS_A_SENTENCE = /[.!?:;]$/;
const SENTENCE = /[^.!?]+[.!?]*|[.!?]+/g;

function tableCellsToText(_row: string, cells: string): string {
  return cells
    .split("|")
    .map((cell) => cell.trim())
    .filter((cell) => cell.length > 0)
    .join(", ");
}

function boldText(_match: string, starred?: string, underscored?: string): string {
  return starred ?? underscored ?? "";
}

function collapseSpaces(line: string): string {
  return line.replace(/\s+/g, " ").trim();
}

function endSentence(line: string): string {
  return ENDS_A_SENTENCE.test(line) ? line : `${line}.`;
}

function toSpeakableText(markdown: string): string {
  return markdown
    .replace(CODE_BLOCK, CODE_BLOCK_REPLACEMENT)
    .replace(HORIZONTAL_RULE, "")
    .replace(TABLE_DIVIDER, "")
    .replace(TABLE_ROW, tableCellsToText)
    .replace(INLINE_CODE, "$1")
    .replace(IMAGE_OR_LINK, "$1")
    .replace(AUTOLINK, "")
    .replace(BARE_URL, "link")
    .replace(HTML_TAG, "")
    .replace(HEADING, "")
    .replace(BLOCKQUOTE, "")
    .replace(LIST_MARKER, "")
    .replace(BOLD, boldText)
    .replace(STRIKETHROUGH, "$1")
    .replace(ITALIC_STARS, "$1")
    .replace(ITALIC_UNDERSCORES, "$1$2")
    .replace(EMOJI, "")
    .replace(SPACE_BEFORE_PUNCTUATION, "$1")
    .split("\n")
    .map(collapseSpaces)
    .filter((line) => line.length > 0)
    .map(endSentence)
    .join("\n");
}

function sentencesOf(plainText: string): string[] {
  return plainText
    .split("\n")
    .flatMap((line) => line.match(SENTENCE) ?? [])
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);
}

function sliceWord(word: string, maxLength: number): string[] {
  const slices: string[] = [];
  for (let start = 0; start < word.length; start += maxLength) {
    slices.push(word.slice(start, start + maxLength));
  }
  return slices;
}

function packChunks(parts: string[]): string[] {
  const chunks: string[] = [];
  let current = "";
  for (const part of parts) {
    if (current === "") {
      current = part;
    } else if (current.length + 1 + part.length <= MAX_CHUNK_LENGTH) {
      current = `${current} ${part}`;
    } else {
      chunks.push(current);
      current = part;
    }
  }
  if (current !== "") chunks.push(current);
  return chunks;
}

function fitSentence(sentence: string): string[] {
  return packChunks(sentence.split(" ").flatMap((word) => sliceWord(word, MAX_CHUNK_LENGTH)));
}

export function prepareSpeechChunks(markdown: string): string[] {
  return packChunks(sentencesOf(toSpeakableText(markdown)).flatMap(fitSentence));
}
