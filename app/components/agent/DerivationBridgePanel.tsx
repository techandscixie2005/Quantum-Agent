"use client";

import type { DerivationBridge } from "../teaching/derivation";
import type { EvidencePacket } from "../teaching/contracts";
import { AgentEquation } from "./AgentEquation";
import styles from "./agent.module.css";

export function DerivationBridgePanel({ bridge, evidence }: { bridge: DerivationBridge; evidence: EvidencePacket }) {
  return (
    <section className={`${styles.derivationSheet} ${styles.bridgeSheet}`} aria-label="结构化推导桥" data-testid="derivation-bridge">
      <p className={styles.kicker}>DERIVATION BRIDGE</p>
      <h2>补上两行之间的逻辑</h2>
      <p>以下中间步骤为模型提出的推导支架，尚未经教师审核或科学工具验证。</p>
      <AgentEquation latex={bridge.source_step} />
      {bridge.missing_steps.map((step, index) => (
        <details key={index}>
          <summary>展开第 {index + 1} 步：{step.justification}</summary>
          <AgentEquation latex={step.formula} />
          {step.source_refs.map((ref, i) => {
            const item = evidence.evidence.find((entry) => entry.evidence_id === ref.evidence_id);
            return <blockquote key={i}>{ref.quote}<footer>{item?.document_title} · {item?.locator.physical_page ? `第 ${item.locator.physical_page} 页` : item?.source_file_name}</footer></blockquote>;
          })}
        </details>
      ))}
      {bridge.partial ? <p>其余步骤留给你重构：请在下方尝试区写出下一步及其依据。</p> : null}
      <p>目标式</p><AgentEquation latex={bridge.target_step} />
      {([
        ["定义", bridge.used_definitions], ["假设", bridge.assumptions],
        ["前置知识", bridge.prerequisites], ["适用条件", bridge.validity_conditions],
      ] as const).map(([label, values]) => values.length ? (
        <details key={label}><summary>{label}</summary><ul>{values.map((value, i) => <li key={i}>{value}</li>)}</ul></details>
      ) : null)}
    </section>
  );
}
