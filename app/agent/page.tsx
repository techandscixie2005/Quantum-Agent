import type { Metadata } from "next";

import { AgentExperience } from "@/app/components/agent/AgentExperience";
import { AgentQueryProvider } from "@/app/components/agent/AgentQueryProvider";

export const metadata: Metadata = {
  title: "Quantum Agent · 科学学习工作台",
  description: "面向 USTC 量子物理课程的多模态、证据驱动教学 Agent。",
};

export default function AgentPage() {
  return (
    <AgentQueryProvider>
      <AgentExperience />
    </AgentQueryProvider>
  );
}

