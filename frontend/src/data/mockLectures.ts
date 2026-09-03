import type { ChatMessage, Lecture, ProcessingStep } from "../types/lecture";

export const processingSteps: ProcessingStep[] = [
  { id: "upload", title: "文件上传完成", description: "lecture-05-introduction.mp4 · 1.2 GB", state: "complete", detail: "刚刚" },
  { id: "transcript", title: "转写已就绪", description: "已完成自动语音识别", state: "complete", detail: "刚刚" },
  { id: "slides", title: "幻灯片识别中", description: "正在从幻灯片提取文字", state: "working", detail: "45%" },
  { id: "index", title: "检索索引构建", description: "正在为快速检索准备内容", state: "pending", detail: "等待中" },
  { id: "summary", title: "摘要待生成", description: "正在生成课程要点", state: "pending", detail: "等待中" },
];

export const lectures: Lecture[] = [
  {
    id: "transformer-internals",
    title: "Lecture 11: Transformer 内部机制与位置编码",
    source: "Stanford CS224n: NLP with Deep Learning",
    year: "2023",
    duration: "23:47",
    timeRange: "32:14 – 36:58",
    timestamp: "32:14",
    preview: "这里我们比较旋转位置编码（RoPE）与正弦位置编码。RoPE 通过旋转复数空间中的查询和键来编码位置，因此在长序列外推中表现更好。",
    visual: "rope",
  },
  {
    id: "attention-deep-dive",
    title: "Attention Is All You Need（深入解读）",
    source: "MIT 6.S898: Advanced NLP",
    year: "2022",
    duration: "18:35",
    timeRange: "45:07 – 50:12",
    timestamp: "45:07",
    preview: "课程讨论了不同的位置编码方案，包括原始的正弦位置编码和 RoPE 等变体，并解释它们为何会影响模型的长度泛化能力。",
    visual: "attention",
  },
  {
    id: "efficient-transformers",
    title: "高效 Transformer 与后续发展",
    source: "CMU 11-747: Deep Learning Systems",
    year: "2023",
    duration: "15:02",
    timeRange: "12:43 – 16:24",
    timestamp: "12:43",
    preview: "RoPE 会根据位置相关的角度旋转查询和键向量，在保持点积关系的同时提供相对位置信息。",
    visual: "rope",
  },
  {
    id: "sequence-modeling",
    title: "Transformer 中的序列建模",
    source: "Google AI Residency Talk",
    year: "2021",
    duration: "21:09",
    timeRange: "28:10 – 32:05",
    timestamp: "28:10",
    preview: "本节分析正弦位置编码与 RoPE 的对比，并讨论两者在下游任务和长上下文中的差异。",
    visual: "sequence",
  },
];

export const transcript = [
  { time: "12:31", content: "科学的核心是一个简单的循环。我们从观察周围的世界开始，留意其中的规律和异常。" },
  { time: "12:47", content: "从这些观察出发，我们提出问题——那些帮助我们解释所见、引导我们深入理解的好问题。", active: true },
  { time: "13:03", content: "接下来，我们提出假设。它不只是一个猜测，而是对世界做出明确预测、可以被检验的解释。" },
  { time: "13:19", content: "随后通过实验或数据收集来检验假设。结果可能支持它、挑战它，也可能带来新的问题。" },
  { time: "13:48", content: "最后，我们分析结果、得出结论，并用所学知识为下一轮探索提供方向。" },
];

export const initialChat: ChatMessage[] = [
  { id: "q1", role: "user", content: "什么是科学方法？", time: "14:14" },
  { id: "a1", role: "assistant", content: "科学方法是一套系统认识自然世界的循环：观察现象、提出问题、形成可检验的假设，再通过实验或数据收集进行分析。证据会帮助我们修正解释，并引出下一轮问题。", time: "14:14" },
  { id: "q2", role: "user", content: "为什么假设必须是可证伪的？", time: "14:15" },
  { id: "a2", role: "assistant", content: "可证伪性让假设能够接受检验：如果没有任何观察或实验可能挑战它，我们就无法用证据判断它是否可靠。它也是区分科学主张与无法验证观点的重要标准。", time: "14:15" },
];
