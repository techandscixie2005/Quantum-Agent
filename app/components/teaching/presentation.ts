import type {
  SupportBasis,
  TeachingMode,
  WorkflowStepName,
} from "./contracts";

export const MODE_COPY: Record<
  TeachingMode,
  Readonly<{
    index: string;
    label: string;
    short: string;
    title: string;
    description: string;
    messageLabel: string;
    messageHint: string;
    attemptLabel: string;
    attemptHint: string;
  }>
> = {
  learn_concepts: {
    index: "CONCEPT",
    label: "Learn Concepts",
    short: "学概念",
    title: "从课程证据建立物理图像",
    description: "定位相关概念与先修知识，再依据已发布课程材料解释，并留下一个可检查理解的问题。",
    messageLabel: "你想理解什么？",
    messageHint: "例如：波函数的统计解释是什么？它与概率密度有什么关系？",
    attemptLabel: "你目前的理解（可选）",
    attemptHint: "写下你的解释、困惑或已经尝试过的判断，系统只把它作为诊断线索。",
  },
  review_derivations: {
    index: "DERIVATION",
    label: "Review Derivations",
    short: "看推导",
    title: "逐步检查推导，而不是直接交付答案",
    description: "将目标与当前推导步骤分开提交；课程答案政策决定返回问题、提示、脚手架或完整说明。",
    messageLabel: "要检查的推导目标",
    messageHint: "例如：检查从定态薛定谔方程到能量本征值的这一步。",
    attemptLabel: "你的推导步骤",
    attemptHint: "粘贴实际推导、变量约定与卡住的位置。一次提交一个关键步骤最容易定位问题。",
  },
  run_experiments: {
    index: "EXPERIMENT",
    label: "Run Experiments",
    short: "做实验",
    title: "先做物理预测，再运行受限计算",
    description: "用类型化参数请求符号、数值或双能级模拟；结果会标明工具、状态、输入摘要和局限。",
    messageLabel: "实验问题与预期",
    messageHint: "例如：失谐为零时，初态 |0〉 的占据概率应如何随时间变化？",
    attemptLabel: "你的预测或计算（推荐填写）",
    attemptHint: "先写下趋势、极值或守恒量预测。答案政策可能要求观察到尝试后才运行工具。",
  },
  work_on_projects: {
    index: "PROJECT",
    label: "Work on Projects",
    short: "做项目",
    title: "把课程项目拆成可验证的下一步",
    description: "围绕当前里程碑检索课程概念、给出小步行动，并记录学生提交的真实学习证据。",
    messageLabel: "当前里程碑与阻碍",
    messageHint: "例如：我要验证隧穿波包的概率守恒，目前卡在边界条件的选取。",
    attemptLabel: "已有产物或决策记录（可选）",
    attemptHint: "写下已完成的计算、实验设置或代码测试结论；不要粘贴密钥或个人数据。",
  },
};

export const WORKFLOW_LABELS: Record<WorkflowStepName, string> = {
  classify_task: "任务分类",
  identify_concepts: "识别概念",
  retrieve_evidence: "检索课程证据",
  diagnose_progress: "诊断当前进展",
  choose_teaching_action: "选择教学动作",
  apply_answer_policy: "执行答案政策",
  run_scientific_tools: "运行科学工具",
  generate_response: "生成教学回应",
  validate_response: "校验证据与声明",
  record_learning_evidence: "记录学习证据",
};

export const SUPPORT_LABELS: Record<SupportBasis, string> = {
  course_material: "课程材料",
  symbolic_verification: "符号验证",
  numerical_verification: "数值验证",
  simulation: "模拟",
  code_test: "代码测试",
  pedagogical_prompt: "教学引导",
  unverified_model_inference: "未验证模型推断",
};

export const RELEASE_LABELS = {
  question_only: "只返回诊断问题",
  hint: "渐进提示",
  scaffold: "解题脚手架",
  full_explanation: "完整概念说明",
  full_solution: "完整解答",
} as const;

export const STATUS_LABELS = {
  grounded: "课程证据充分",
  mixed: "混合证据",
  model_degraded: "模型降级",
  insufficient_course_evidence: "课程证据不足",
} as const;

export function reasonLabel(reason: string): string {
  const known: Record<string, string> = {
    conceptual_explanation_allowed: "概念解释可按课程政策完整释放",
    no_attempt_observed: "尚未观察到学生尝试，先返回提示",
    scaffold_threshold_met: "已达到脚手架所需尝试次数",
    full_solution_threshold_met: "教师允许且已达到完整解答阈值",
    full_solution_disabled: "教师政策未开放完整解答",
    diagnostic_question_required: "需要先通过诊断问题确认理解",
  };
  return known[reason] ?? "后端答案政策给出了此释放级别";
}

