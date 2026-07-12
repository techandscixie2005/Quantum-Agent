export type ProjectDefinition = {
  id: string;
  title: string;
  question: string;
  level: "golden-loop" | "runnable-module" | "teaching-design";
  milestones: string[];
  validators: string[];
};

export const projectDefinitions: ProjectDefinition[] = [
  {
    id: "tunneling-wavepacket",
    title: "量子隧穿与波包传播",
    question: "有限宽度高斯波包撞向势垒时，反射、透射、干涉和展宽如何发生？",
    level: "golden-loop",
    milestones: ["初始波包与归一化", "自由传播", "加入矩形势垒", "反射与透射概率", "参数扫描", "WKB 对照", "物理解读"],
    validators: ["normalization", "probability_conservation", "boundary_continuity", "convergence"],
  },
  {
    id: "hydrogen-stark-zeeman",
    title: "氢原子轨道、简并与外场微扰",
    question: "量子数、轨道形状、节点和能级简并之间有什么关系？外场如何打破简并？",
    level: "runnable-module",
    milestones: ["径向波函数", "径向概率分布", "球谐函数", "节点结构", "简并子空间", "微扰矩阵", "能级劈裂"],
    validators: ["normalization", "orthogonality", "hermiticity", "eigen_residual"],
  },
  {
    id: "helium-variational",
    title: "变分法与氦原子的有效核电荷",
    question: "无法精确求解多电子体系时，如何用物理直觉构造可检验的近似？",
    level: "teaching-design",
    milestones: ["能量期望值", "能量分解", "扫描 Zeff", "寻找最优点", "变分上界", "屏蔽解释", "相关因子"],
    validators: ["normalization", "variational_bound", "numerical_stability"],
  },
  {
    id: "diatomic-mo-spectra",
    title: "双原子分子的分子轨道与振转光谱",
    question: "如何从原子轨道的线性组合得到成键、势能曲线和可观测光谱？",
    level: "teaching-design",
    milestones: ["重叠积分", "成键与反键轨道", "电子密度", "势能曲线", "平衡键长", "Morse 振动", "振转光谱"],
    validators: ["normalization", "symmetry", "dissociation_limit", "spectrum_index"],
  },
];

