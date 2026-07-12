import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const sourceDir = path.resolve(root, "courseware-source/text");
const outputFile = path.resolve(root, "lib/courseware.generated.json");

const sources = [
  {
    file: "第1-2章(3).txt",
    id: "qp-ch01-02",
    title: "第1–2章：原子模型、旧量子论与量子力学基础",
    chapter: "第一、二章",
    pdf: "/courseware/01-02-foundations.pdf",
    topics: ["原子模型", "旧量子论", "波粒二象性", "波函数", "薛定谔方程", "一维势场", "量子隧穿"],
  },
  {
    file: "第三章 单电子原子 (3).txt",
    id: "qp-ch03",
    title: "第三章：单电子原子",
    chapter: "第三章",
    pdf: "/courseware/03-one-electron-atoms.pdf",
    topics: ["中心力场", "氢原子", "角动量", "电子自旋", "角动量耦合", "精细结构", "维里定理"],
  },
  {
    file: "第4章(2)(3).txt",
    id: "qp-ch04",
    title: "第四章：表象理论与矩阵形式的量子力学",
    chapter: "第四章",
    pdf: "/courseware/04-representation-theory.pdf",
    topics: ["力学量表象", "态矢量", "算符矩阵", "表象变换", "Dirac符号", "角动量矩阵"],
  },
  {
    file: "第五章 微扰理论(3).txt",
    id: "qp-ch05",
    title: "第五章：微扰理论",
    chapter: "第五章",
    pdf: "/courseware/05-perturbation-theory.pdf",
    topics: ["非简并微扰", "简并微扰", "变分法", "Stark效应", "含时微扰", "量子跃迁"],
  },
  {
    file: "第六章 多电子原子 (3).txt",
    id: "qp-ch06",
    title: "第六章：多电子原子",
    chapter: "第六章",
    pdf: "/courseware/06-many-electron-atoms.pdf",
    topics: ["多电子原子", "中心力场近似", "变分原理", "交换反对称性", "Pauli原理", "原子光谱项"],
  },
  {
    file: "第七章 双原子分子(3).txt",
    id: "qp-ch07",
    title: "第七章：双原子分子",
    chapter: "第七章",
    pdf: "/courseware/07-diatomic-molecules.pdf",
    topics: ["氢分子离子", "线性变分", "分子轨道", "价键理论", "电子结构", "电子谱项"],
  },
  {
    file: "第八章 分子光谱(3).txt",
    id: "qp-ch08",
    title: "第八章：分子光谱基本原理",
    chapter: "第八章",
    pdf: "/courseware/08-molecular-spectroscopy.pdf",
    topics: ["光与物质相互作用", "转动光谱", "振动光谱", "电子光谱", "选择定则", "Raman光谱"],
  },
];

const vocabulary = [
  "波函数", "薛定谔", "本征值", "本征态", "概率密度", "归一化", "厄米", "对易", "不确定关系",
  "势垒", "隧穿", "透射", "谐振子", "中心力场", "径向分布", "球谐函数", "氢原子", "角动量", "自旋",
  "耦合", "精细结构", "表象", "矩阵", "Dirac", "微扰", "非简并", "简并", "Stark", "跃迁", "变分",
  "多电子", "交换", "反对称", "Pauli", "光谱项", "分子轨道", "价键", "LCAO", "成键", "反键",
  "转动光谱", "振动光谱", "电子光谱", "选择定则", "Raman", "红外", "Franck-Condon", "Born-Oppenheimer", "对角化",
];

function normalizePage(text) {
  return text
    .replace(/\r/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^\s+|\s+$/g, "");
}

function inferHeading(text, fallback) {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const preferred = lines.find((line) => /^(第[一二三四五六七八九十\d]+章|§?\s*\d+[—\-－]\d+|[一二三四五六七八九十]+、)/.test(line));
  return (preferred ?? lines.find((line) => line.length >= 4 && line.length <= 42) ?? fallback).slice(0, 80);
}

function chunksForPage(text, max = 1250, overlap = 160) {
  if (text.length <= max) return [text];
  const chunks = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + max, text.length);
    if (end < text.length) {
      const paragraph = text.lastIndexOf("\n", end);
      if (paragraph > start + Math.floor(max * 0.62)) end = paragraph;
    }
    chunks.push(text.slice(start, end).trim());
    if (end >= text.length) break;
    start = Math.max(end - overlap, start + 1);
  }
  return chunks.filter((chunk) => chunk.length >= 30);
}

const manifest = [];
const chunks = [];

for (const source of sources) {
  const raw = await readFile(path.join(sourceDir, source.file), "utf8");
  const pages = raw.split("\f").map(normalizePage);
  if (!pages.at(-1)) pages.pop();
  const checksum = createHash("sha256").update(raw).digest("hex");
  manifest.push({
    id: source.id,
    title: source.title,
    chapter: source.chapter,
    pageCount: pages.length,
    pdfUrl: source.pdf,
    topics: source.topics,
    checksum,
  });
  pages.forEach((pageText, pageIndex) => {
    if (pageText.length < 24) return;
    const pageNumber = pageIndex + 1;
    const heading = inferHeading(pageText, `${source.chapter} · 第 ${pageNumber} 页`);
    const keywords = [...new Set([
      ...source.topics.filter((term) => pageText.toLowerCase().includes(term.toLowerCase())),
      ...vocabulary.filter((term) => pageText.toLowerCase().includes(term.toLowerCase())),
    ])].slice(0, 18);
    chunksForPage(pageText).forEach((content, chunkIndex) => {
      chunks.push({
        id: `${source.id}-p${String(pageNumber).padStart(3, "0")}-${chunkIndex + 1}`,
        sourceId: source.id,
        courseId: "qp-2026-spring",
        title: source.title,
        chapter: `${source.chapter} · ${heading}`,
        pages: String(pageNumber),
        pageNumber,
        sourceUrl: `${source.pdf}#page=${pageNumber}`,
        content,
        keywords,
        status: "published",
      });
    });
  });
}

await mkdir(path.dirname(outputFile), { recursive: true });
await writeFile(outputFile, `${JSON.stringify({ generatedAt: new Date().toISOString(), manifest, chunks }, null, 2)}\n`, "utf8");
console.log(`Indexed ${manifest.length} courseware files into ${chunks.length} page-aware chunks.`);
