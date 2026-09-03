import { Icon } from "../../components/Icon";
import type { ProcessingStep } from "../../types/lecture";

interface ProcessingStepsProps {
  steps: ProcessingStep[];
}

export function ProcessingSteps({ steps }: ProcessingStepsProps) {
  return (
    <section className="processing-panel" aria-labelledby="processing-title">
      <h2 id="processing-title">处理进度</h2>
      <ol className="processing-list">
        {steps.map((step) => (
          <li className={`processing-step processing-step--${step.state}`} key={step.id}>
            <span className="step-indicator">{step.state === "complete" && <Icon name="check" />}</span>
            <span className="step-copy"><strong>{step.title}</strong><small>{step.description}</small></span>
            <span className="step-detail">{step.detail}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
