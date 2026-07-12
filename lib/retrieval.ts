import type { Citation } from "./types";
import type { KnowledgeChunk } from "./course-knowledge";

const expansions: Record<string, string[]> = {
  "薛定谔": ["S-方程", "Schrödinger"],
  "分子轨道": ["MO法", "LCAO", "成键轨道", "反键轨道"],
  "微扰": ["一级修正", "二级修正"],
  "光谱": ["跃迁", "选择定则", "转动", "振动", "电子光谱"],
  "氢原子": ["单电子原子", "类氢", "中心力场"],
  "矩阵": ["表象", "矩阵力学", "Dirac"],
  "隧穿": ["势垒", "透射", "反射", "衰减"],
};

const salientVocabulary = ["对角化", "简并", "非简并", "微扰", "分子轨道", "成键", "反键", "Franck-Condon", "角动量", "矩阵", "表象", "自旋", "氢原子", "多电子", "交换", "反对称", "选择定则", "转动光谱", "振动光谱", "电子光谱", "变分", "薛定谔", "归一化"];

function normalize(text: string) {
  return text.toLowerCase().replace(/[\s，。！？、；：,.!?;:()（）\[\]{}·—\-]/g, "");
}

function bigrams(text: string) {
  const value = normalize(text);
  const grams = new Set<string>();
  for (let i = 0; i < value.length - 1; i += 1) grams.add(value.slice(i, i + 2));
  return grams;
}

function expandedQuery(query: string) {
  const additions = Object.entries(expansions)
    .filter(([term]) => query.toLowerCase().includes(term.toLowerCase()))
    .flatMap(([, values]) => values);
  return `${query} ${additions.join(" ")}`;
}

function excerpt(text: string, query: string, limit = 620) {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  const terms = expandedQuery(query).split(/\s+/).filter((term) => term.length >= 2);
  const first = terms.map((term) => compact.toLowerCase().indexOf(term.toLowerCase())).filter((index) => index >= 0).sort((a, b) => a - b)[0] ?? 0;
  const start = Math.max(0, first - 90);
  return `${start ? "…" : ""}${compact.slice(start, start + limit)}…`;
}

export function retrieveKnowledge(query: string, chunks: KnowledgeChunk[], limit = 4): Citation[] {
  const expanded = expandedQuery(query);
  const normalized = normalize(expanded);
  const queryGrams = bigrams(expanded);
  return chunks
    .filter((chunk) => chunk.status === "published")
    .map((chunk) => {
      const title = normalize(`${chunk.title}${chunk.chapter}${chunk.keywords.join("")}`);
      const body = normalize(chunk.content);
      let phraseScore = 0;
      for (const keyword of chunk.keywords) {
        const term = normalize(keyword);
        if (term.length > 1 && normalized.includes(term)) phraseScore += title.includes(term) ? 8 : 4;
      }
      const queryTerms = expanded.split(/[\s，。！？、；：,.!?;:()（）]+/).map(normalize).filter((term) => term.length >= 2);
      for (const term of queryTerms) {
        if (title.includes(term)) phraseScore += 6;
        else if (body.includes(term)) phraseScore += 2;
      }
      for (const term of salientVocabulary) {
        if (!query.toLowerCase().includes(term.toLowerCase())) continue;
        const normalizedTerm = normalize(term);
        if (title.includes(normalizedTerm)) phraseScore += 16;
        else if (body.includes(normalizedTerm)) phraseScore += 10;
      }
      if (query.includes("简并") && !query.includes("非简并") && body.includes(normalize("非简并")) && !/简并态|简并情况|简并能级/.test(chunk.content)) phraseScore -= 12;
      let overlap = 0;
      for (const gram of queryGrams) if (title.includes(gram) || body.includes(gram)) overlap += 1;
      const diceLike = overlap / Math.max(queryGrams.size, 1);
      return { chunk, score: phraseScore + diceLike * 3, phraseScore, diceLike };
    })
    .filter(({ score, phraseScore, diceLike }) => score > 3.5 && (phraseScore > 0 || diceLike > 0.58))
    .sort((a, b) => b.score - a.score || (a.chunk.pageNumber ?? 0) - (b.chunk.pageNumber ?? 0))
    .slice(0, limit)
    .map(({ chunk, score }) => ({
      id: chunk.id,
      title: chunk.title,
      chapter: chunk.chapter,
      pages: chunk.pages,
      excerpt: excerpt(chunk.content, query),
      score: Number(score.toFixed(3)),
      sourceUrl: chunk.sourceUrl,
    }));
}
