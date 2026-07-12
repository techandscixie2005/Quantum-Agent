# 5-Minute Live Demo Script

**Setup**: Quantum Agent running locally (`npm run dev`), teacher password configured, viewing the student workspace in browser.

## Step 1: Fast concept question (0:00-0:30)

> "量子物理课上，学生最常问的问题之一：Franck-Condon原理到底是什么？"

- Click "问概念" mode, select "快速问答" capability.
- Type: "什么是Franck-Condon原理？"
- Hit send.

**Show**: The right panel populates with a courseware citation from Chapter 8, page 60. The citation has a clickable link to the original PDF. The answer has six structured fields: conclusion, physical picture, mathematics, misconception, check question, suggested action.

**Competition point**: This is not a chatbot reply. It's a teaching workflow with real course evidence.

## Step 2: Derivation error diagnosis (0:30-1:00)

- Switch to "看推导" mode.
- Show the three derivation steps - step 2 has a warning marker.
- The diagnosis panel flags: "势垒区的衰减常数与外部波数混用了."

**Competition point**: The system locates the first critical error, doesn't just say "you're wrong."

## Step 3: Image analysis (1:00-1:40)

- Switch to "问概念" mode, select "图片识别" capability.
- Upload a sample image (handwritten equation or diagram).
- Type: "解释这个图里的物理内容."

**Show**: The image appears in the composer. Capability-based routing - student chose "图片识别", not "qwen3.6-chat."

## Step 4: Coding project (1:40-2:20)

- Switch to "做项目" mode.
- Show project overview: "量子隧穿与波包传播", 5 milestones, 58% complete.
- Click into Milestone 3: "验证概率守恒."

**Competition point**: Project-based learning with milestones, validators, and progress tracking.

## Step 5: Teacher dashboard (2:20-2:50)

- Click profile button, switch to teacher mode.
- Login form appears (password gate). Enter teacher password.
- Show dashboard: misconception map, TA queue, trajectory replay.

**Competition point**: Password-protected teacher access, not a frontend toggle.

## Step 6: Deterministic fallback (2:50-3:20)

- Demonstrate that even without API keys, the teaching workflow works.
- Send a question: "delta函数势的束缚态能量是多少？"
- Show structured answer with all 6 teaching fields, model source: "deterministic-fallback."

**Competition point**: Teaching workflow never breaks. No API key needed for course-grounded, pedagogically-structured answers.

## Step 7: Wrap-up (3:20-3:30)

> "Quantum Agent 不是套壳聊天框。它是一个可验证、可追踪、可审计的教学工作流。LLM 只负责写解释；教学决策、证据引用、科学验证、模型路由、隐私控制全部由确定性代码控制."