import type { ChatMessage, LectureDetail, ProcessingStep, TranscriptSegment } from "../types/lecture";

export const processingSteps: ProcessingStep[] = [
  { id: "upload", title: "文件上传完成", description: "lecture-05-introduction.mp4 · 1.2 GB", state: "complete", detail: "刚刚" },
  { id: "transcript", title: "转写已就绪", description: "已完成自动语音识别", state: "complete", detail: "刚刚" },
  { id: "slides", title: "幻灯片识别中", description: "正在从幻灯片提取文字", state: "working", detail: "45%" },
  { id: "index", title: "检索索引构建", description: "正在为快速检索准备内容", state: "pending", detail: "等待中" },
  { id: "summary", title: "摘要待生成", description: "正在生成课程要点", state: "pending", detail: "等待中" },
];

const ropeTranscript: TranscriptSegment[] = [
  { id: "rope-1", startMs: 1_920_000, endMs: 1_934_000, content: "在比较位置编码之前，我们先回顾注意力机制为什么需要知道词元在序列中的位置。" },
  { id: "rope-2", startMs: 1_934_000, endMs: 1_953_000, content: "正弦位置编码把不同频率的正弦和余弦值加到输入表示上，提供绝对位置信息。" },
  { id: "rope-3", startMs: 1_953_000, endMs: 1_976_000, content: "RoPE 则根据位置相关角度旋转查询和键，让它们的点积自然携带相对位置关系。" },
  { id: "rope-4", startMs: 1_976_000, endMs: 2_004_000, content: "这种旋转保持向量范数，并让注意力分数只依赖词元之间的相对距离。" },
  { id: "rope-5", startMs: 2_004_000, endMs: 2_032_000, content: "实践中 RoPE 往往有更好的长度外推能力，但仍需结合训练长度和缩放策略判断。" },
];

const qaRules = [
  {
    keywords: ["rope", "旋转", "相对位置"],
    answer: "RoPE 会按位置相关的角度旋转查询和键，使注意力点积直接编码两个词元的相对距离，同时保持向量范数。",
    citationMs: 1_953_000,
  },
  {
    keywords: ["正弦", "区别", "差异"],
    answer: "正弦位置编码向输入加入绝对位置向量；RoPE 把位置信息作用在查询和键的旋转上，因此更自然地表达相对位置。",
    citationMs: 1_934_000,
  },
  {
    keywords: ["外推", "长序列", "长度"],
    answer: "课程指出 RoPE 通常更利于长度外推，不过效果仍受训练上下文长度和推理时缩放方法影响。",
    citationMs: 2_004_000,
  },
];

const makeLecture = (
  lecture: Omit<LectureDetail, "transcript" | "qaRules">,
): LectureDetail => ({ ...lecture, transcript: ropeTranscript, qaRules });

export const lectures: LectureDetail[] = [
  makeLecture({
    id: "transformer-internals",
    title: "Lecture 11: Transformer 内部机制与位置编码",
    source: "Stanford CS224n: NLP with Deep Learning",
    year: "2023",
    duration: "1:02:18",
    durationMs: 3_738_000,
    timeRange: "32:14 – 36:58",
    timestamp: "32:14",
    timestampMs: 1_934_000,
    preview: "这里我们比较旋转位置编码（RoPE）与正弦位置编码。RoPE 通过旋转查询和键来编码位置，因此在长序列外推中表现更好。",
    visual: "rope",
  }),
  makeLecture({
    id: "attention-deep-dive",
    title: "Attention Is All You Need（深入解读）",
    source: "MIT 6.S898: Advanced NLP",
    year: "2022",
    duration: "1:18:35",
    durationMs: 4_715_000,
    timeRange: "45:07 – 50:12",
    timestamp: "45:07",
    timestampMs: 2_707_000,
    preview: "课程讨论了不同的位置编码方案，包括原始的正弦位置编码和 RoPE 等变体，并解释它们为何会影响模型的长度泛化能力。",
    visual: "attention",
  }),
  makeLecture({
    id: "efficient-transformers",
    title: "高效 Transformer 与后续发展",
    source: "CMU 11-747: Deep Learning Systems",
    year: "2023",
    duration: "52:02",
    durationMs: 3_122_000,
    timeRange: "12:43 – 16:24",
    timestamp: "12:43",
    timestampMs: 763_000,
    preview: "RoPE 会根据位置相关的角度旋转查询和键向量，在保持点积关系的同时提供相对位置信息。",
    visual: "rope",
  }),
  makeLecture({
    id: "sequence-modeling",
    title: "Transformer 中的序列建模",
    source: "Google AI Residency Talk",
    year: "2021",
    duration: "1:01:09",
    durationMs: 3_669_000,
    timeRange: "28:10 – 32:05",
    timestamp: "28:10",
    timestampMs: 1_690_000,
    preview: "本节分析正弦位置编码与 RoPE 的对比，并讨论两者在下游任务和长上下文中的差异。",
    visual: "sequence",
  }),
];

export const initialChat: ChatMessage[] = [
  { id: "q1", role: "user", content: "RoPE 和正弦位置编码有什么区别？", time: "14:14" },
  { id: "a1", role: "assistant", content: qaRules[1].answer, time: "14:14", citationMs: qaRules[1].citationMs },
];
