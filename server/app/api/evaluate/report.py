"""
Report generation for RAG evaluation results.

Supports multiple output formats: JSON, CSV, Markdown, and HTML.
"""

import json
import csv
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from api.evaluate.models import (
    EvaluationRun,
    RAGMode,
    QuestionResult,
    AggregateMetrics,
)

logger = logging.getLogger('LectureMind')


class EvaluationReport:
    """
    Generates evaluation reports in various formats.
    """

    def __init__(self, evaluation_run: EvaluationRun):
        """
        Initialize the report generator.

        Args:
            evaluation_run: The completed evaluation run to report on
        """
        self.evaluation_run = evaluation_run

    def save(self, output_path: str, format: Optional[str] = None) -> str:
        """
        Save the report to a file.

        Args:
            output_path: Path to save the report
            format: Output format (json, csv, md, html). Auto-detected from extension if not provided.

        Returns:
            Path to the saved file
        """
        path = Path(output_path)

        # Auto-detect format from extension
        if format is None:
            format = path.suffix.lstrip('.')

        format = format.lower()

        if format == 'json':
            return self._save_json(path)
        elif format == 'csv':
            return self._save_csv(path)
        elif format in ('md', 'markdown'):
            return self._save_markdown(path)
        elif format == 'html':
            return self._save_html(path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _save_json(self, path: Path) -> str:
        """Save report as JSON."""
        data = self.evaluation_run.to_dict()

        # Add summary statistics
        data["summary"] = self._generate_summary()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"JSON report saved to {path}")
        return str(path)

    def _save_csv(self, path: Path) -> str:
        """Save report as CSV (detailed results)."""
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'question_id',
                'question',
                'question_type',
                'difficulty',
                'ground_truth',
                'llm_direct_answer',
                'llm_direct_score',
                'llm_direct_hallucination',
                'fast_rag_answer',
                'fast_rag_score',
                'fast_rag_hallucination',
                'agentic_rag_answer',
                'agentic_rag_score',
                'agentic_rag_hallucination',
            ])

            # Data rows
            for qr in self.evaluation_run.question_results:
                row = [
                    qr.qa_pair.id,
                    qr.qa_pair.question,
                    qr.qa_pair.question_type,
                    qr.qa_pair.difficulty,
                    qr.qa_pair.ground_truth_answer,
                ]

                # Add results for each mode
                for mode in [RAGMode.LLM_DIRECT, RAGMode.FAST_RAG, RAGMode.AGENTIC_RAG]:
                    if mode in qr.responses and mode in qr.evaluations:
                        response = qr.responses[mode]
                        evaluation = qr.evaluations[mode]
                        row.extend([
                            response.answer[:500] if response.answer else "ERROR",
                            evaluation.overall_score,
                            evaluation.hallucination_detected,
                        ])
                    else:
                        row.extend(["N/A", 0, False])

                writer.writerow(row)

        logger.info(f"CSV report saved to {path}")
        return str(path)

    def _save_markdown(self, path: Path) -> str:
        """Save report as Markdown."""
        lines = []

        # Title
        lines.append("# RAG Evaluation Report")
        lines.append("")

        # Metadata
        lines.append("## Evaluation Metadata")
        lines.append(f"- **Video**: {self.evaluation_run.video_title}")
        lines.append(f"- **Video ID**: {self.evaluation_run.video_id}")
        lines.append(f"- **Evaluation ID**: {self.evaluation_run.id}")
        lines.append(f"- **Date**: {self.evaluation_run.created_at}")
        lines.append(f"- **SOTA Model**: {self.evaluation_run.sota_model}")
        lines.append(f"- **Test Model**: {self.evaluation_run.test_model}")
        lines.append(f"- **Number of Questions**: {self.evaluation_run.num_questions}")
        lines.append(f"- **Status**: {self.evaluation_run.status.value}")
        lines.append("")

        # Aggregate Metrics
        lines.append("## Aggregate Metrics")
        lines.append("")
        lines.append("| Mode | Avg Score | Accuracy | Completeness | Hallucination Rate | Avg Response Time |")
        lines.append("|------|-----------|----------|--------------|-------------------|-------------------|")

        for mode in RAGMode:
            if mode in self.evaluation_run.aggregate_metrics:
                m = self.evaluation_run.aggregate_metrics[mode]
                lines.append(
                    f"| {mode.value} | {m.avg_overall_score:.1f} | {m.avg_accuracy_score:.1f} | "
                    f"{m.avg_completeness_score:.1f} | {m.hallucination_rate:.1f}% | "
                    f"{m.avg_response_time_ms:.0f}ms |"
                )

        lines.append("")

        # Hallucination Analysis
        lines.append("## Hallucination Analysis")
        lines.append("")

        baseline_hallucinations = 0
        fast_rag_hallucinations = 0
        agentic_rag_hallucinations = 0

        for qr in self.evaluation_run.question_results:
            if RAGMode.LLM_DIRECT in qr.evaluations and qr.evaluations[RAGMode.LLM_DIRECT].hallucination_detected:
                baseline_hallucinations += 1
            if RAGMode.FAST_RAG in qr.evaluations and qr.evaluations[RAGMode.FAST_RAG].hallucination_detected:
                fast_rag_hallucinations += 1
            if RAGMode.AGENTIC_RAG in qr.evaluations and qr.evaluations[RAGMode.AGENTIC_RAG].hallucination_detected:
                agentic_rag_hallucinations += 1

        total = len(self.evaluation_run.question_results)

        lines.append(f"- **LLM Direct Hallucinations**: {baseline_hallucinations}/{total} ({baseline_hallucinations/total*100:.1f}%)")
        lines.append(f"- **Fast RAG Hallucinations**: {fast_rag_hallucinations}/{total} ({fast_rag_hallucinations/total*100:.1f}%)")
        lines.append(f"- **Agentic RAG Hallucinations**: {agentic_rag_hallucinations}/{total} ({agentic_rag_hallucinations/total*100:.1f}%)")
        lines.append("")

        if baseline_hallucinations > 0:
            fast_reduction = ((baseline_hallucinations - fast_rag_hallucinations) / baseline_hallucinations) * 100
            agentic_reduction = ((baseline_hallucinations - agentic_rag_hallucinations) / baseline_hallucinations) * 100
            lines.append(f"- **Fast RAG Hallucination Reduction**: {fast_reduction:.1f}%")
            lines.append(f"- **Agentic RAG Hallucination Reduction**: {agentic_reduction:.1f}%")

        lines.append("")

        # Detailed Results
        lines.append("## Detailed Results")
        lines.append("")

        for i, qr in enumerate(self.evaluation_run.question_results, 1):
            lines.append(f"### Question {i}: {qr.qa_pair.question}")
            lines.append("")
            lines.append(f"**Type**: {qr.qa_pair.question_type} | **Difficulty**: {qr.qa_pair.difficulty}")
            lines.append("")
            lines.append(f"**Ground Truth**: {qr.qa_pair.ground_truth_answer}")
            lines.append("")

            for mode in [RAGMode.LLM_DIRECT, RAGMode.FAST_RAG, RAGMode.AGENTIC_RAG]:
                if mode in qr.responses and mode in qr.evaluations:
                    response = qr.responses[mode]
                    evaluation = qr.evaluations[mode]

                    lines.append(f"#### {mode.value}")
                    lines.append("")
                    lines.append(f"**Score**: {evaluation.overall_score:.1f}/100")
                    lines.append(f"**Hallucination**: {'Yes' if evaluation.hallucination_detected else 'No'}")
                    lines.append(f"**Response Time**: {response.response_time_ms:.0f}ms")
                    lines.append("")
                    lines.append(f"**Answer**: {response.answer}")
                    lines.append("")

                    if evaluation.hallucination_detected and evaluation.hallucination_details:
                        lines.append(f"**Hallucination Details**: {evaluation.hallucination_details}")
                        lines.append("")

            lines.append("---")
            lines.append("")

        # Write to file
        with open(path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

        logger.info(f"Markdown report saved to {path}")
        return str(path)

    def _save_html(self, path: Path) -> str:
        """Save report as HTML."""
        html = self._generate_html()

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"HTML report saved to {path}")
        return str(path)

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of the evaluation."""
        summary = {
            "video_title": self.evaluation_run.video_title,
            "video_id": self.evaluation_run.video_id,
            "num_questions": self.evaluation_run.num_questions,
            "sota_model": self.evaluation_run.sota_model,
            "test_model": self.evaluation_run.test_model,
            "status": self.evaluation_run.status.value,
        }

        # Add aggregate metrics
        summary["metrics"] = {}
        for mode, metrics in self.evaluation_run.aggregate_metrics.items():
            summary["metrics"][mode.value] = metrics.to_dict()

        # Add hallucination analysis
        baseline_hallucinations = 0
        fast_rag_hallucinations = 0
        agentic_rag_hallucinations = 0

        for qr in self.evaluation_run.question_results:
            if RAGMode.LLM_DIRECT in qr.evaluations and qr.evaluations[RAGMode.LLM_DIRECT].hallucination_detected:
                baseline_hallucinations += 1
            if RAGMode.FAST_RAG in qr.evaluations and qr.evaluations[RAGMode.FAST_RAG].hallucination_detected:
                fast_rag_hallucinations += 1
            if RAGMode.AGENTIC_RAG in qr.evaluations and qr.evaluations[RAGMode.AGENTIC_RAG].hallucination_detected:
                agentic_rag_hallucinations += 1

        total = len(self.evaluation_run.question_results)

        summary["hallucination_analysis"] = {
            "llm_direct_count": baseline_hallucinations,
            "fast_rag_count": fast_rag_hallucinations,
            "agentic_rag_count": agentic_rag_hallucinations,
            "llm_direct_rate": (baseline_hallucinations / total) * 100 if total > 0 else 0,
            "fast_rag_rate": (fast_rag_hallucinations / total) * 100 if total > 0 else 0,
            "agentic_rag_rate": (agentic_rag_hallucinations / total) * 100 if total > 0 else 0,
        }

        if baseline_hallucinations > 0:
            summary["hallucination_analysis"]["fast_rag_reduction_pct"] = (
                ((baseline_hallucinations - fast_rag_hallucinations) / baseline_hallucinations) * 100
            )
            summary["hallucination_analysis"]["agentic_rag_reduction_pct"] = (
                ((baseline_hallucinations - agentic_rag_hallucinations) / baseline_hallucinations) * 100
            )

        return summary

    def _generate_html(self) -> str:
        """Generate HTML report."""
        summary = self._generate_summary()

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>RAG Evaluation Report - {self.evaluation_run.video_title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-card h3 {{
            margin-top: 0;
            color: #333;
        }}
        .score {{
            font-size: 2em;
            font-weight: bold;
            color: #2196F3;
        }}
        .hallucination {{
            color: #f44336;
        }}
        .improvement {{
            color: #4CAF50;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #2196F3;
            color: white;
        }}
        .question-block {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .mode-response {{
            margin: 15px 0;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 4px;
            border-left: 4px solid #2196F3;
        }}
        .mode-response.hallucination {{
            border-left-color: #f44336;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>RAG Evaluation Report</h1>
        <p><strong>Video:</strong> {self.evaluation_run.video_title}</p>
        <p><strong>Evaluation Date:</strong> {self.evaluation_run.created_at}</p>
        <p><strong>SOTA Model:</strong> {self.evaluation_run.sota_model}</p>
        <p><strong>Test Model:</strong> {self.evaluation_run.test_model}</p>
        <p><strong>Questions Evaluated:</strong> {self.evaluation_run.num_questions}</p>
        {f'<p><strong>Total Duration:</strong> {self.evaluation_run.metadata.get("total_duration_seconds", 0):.1f}s</p>' if self.evaluation_run.metadata.get("total_duration_seconds") else ''}
        {f'<p><strong>Concurrency:</strong> {self.evaluation_run.metadata.get("max_workers", 3)} mode workers' + (f', {self.evaluation_run.metadata.get("question_workers", 4)} question workers' if self.evaluation_run.metadata.get("parallel_questions") else '') + '</p>' if self.evaluation_run.metadata.get("max_workers") else ''}
    </div>

    <div class="metrics-grid">
"""

        # Add metric cards for each mode
        for mode in RAGMode:
            if mode in self.evaluation_run.aggregate_metrics:
                m = self.evaluation_run.aggregate_metrics[mode]
                html += f"""
        <div class="metric-card">
            <h3>{mode.value.replace('_', ' ').title()}</h3>
            <div class="score">{m.avg_overall_score:.1f}</div>
            <p>Average Overall Score</p>
            <p>Hallucination Rate: <span class="{'hallucination' if m.hallucination_rate > 20 else ''}">{m.hallucination_rate:.1f}%</span></p>
            <p>Avg Response Time: {m.avg_response_time_ms:.0f}ms</p>
        </div>
"""

        html += """
    </div>

    <h2>Aggregate Metrics Comparison</h2>
    <table>
        <thead>
            <tr>
                <th>Mode</th>
                <th>Avg Score</th>
                <th>Accuracy</th>
                <th>Completeness</th>
                <th>Hallucination Rate</th>
                <th>Error Rate</th>
            </tr>
        </thead>
        <tbody>
"""

        for mode in RAGMode:
            if mode in self.evaluation_run.aggregate_metrics:
                m = self.evaluation_run.aggregate_metrics[mode]
                html += f"""
            <tr>
                <td>{mode.value}</td>
                <td>{m.avg_overall_score:.1f}</td>
                <td>{m.avg_accuracy_score:.1f}</td>
                <td>{m.avg_completeness_score:.1f}</td>
                <td class="{'hallucination' if m.hallucination_rate > 20 else ''}">{m.hallucination_rate:.1f}%</td>
                <td>{m.error_rate:.1f}%</td>
            </tr>
"""

        html += """
        </tbody>
    </table>

    <h2>Hallucination Analysis</h2>
"""

        ha = summary.get("hallucination_analysis", {})
        html += f"""
    <div class="metrics-grid">
        <div class="metric-card">
            <h3>LLM Direct</h3>
            <div class="score hallucination">{ha.get('llm_direct_rate', 0):.1f}%</div>
            <p>Hallucination Rate (Baseline)</p>
        </div>
        <div class="metric-card">
            <h3>Fast RAG</h3>
            <div class="score">{ha.get('fast_rag_rate', 0):.1f}%</div>
            <p>Hallucination Rate</p>
            {'<p class="improvement">↓ {:.1f}% reduction</p>'.format(ha.get('fast_rag_reduction_pct', 0)) if 'fast_rag_reduction_pct' in ha else ''}
        </div>
        <div class="metric-card">
            <h3>Agentic RAG</h3>
            <div class="score">{ha.get('agentic_rag_rate', 0):.1f}%</div>
            <p>Hallucination Rate</p>
            {'<p class="improvement">↓ {:.1f}% reduction</p>'.format(ha.get('agentic_rag_reduction_pct', 0)) if 'agentic_rag_reduction_pct' in ha else ''}
        </div>
    </div>

    <h2>Detailed Results</h2>
"""

        # Add detailed question results
        for i, qr in enumerate(self.evaluation_run.question_results, 1):
            html += f"""
    <div class="question-block">
        <h3>Question {i}: {qr.qa_pair.question}</h3>
        <p><strong>Type:</strong> {qr.qa_pair.question_type} | <strong>Difficulty:</strong> {qr.qa_pair.difficulty}</p>
        <p><strong>Ground Truth:</strong> {qr.qa_pair.ground_truth_answer}</p>
"""

            for mode in [RAGMode.LLM_DIRECT, RAGMode.FAST_RAG, RAGMode.AGENTIC_RAG]:
                if mode in qr.responses and mode in qr.evaluations:
                    response = qr.responses[mode]
                    evaluation = qr.evaluations[mode]
                    is_hallucination = evaluation.hallucination_detected

                    html += f"""
        <div class="mode-response {'hallucination' if is_hallucination else ''}">
            <h4>{mode.value} - Score: {evaluation.overall_score:.1f}/100</h4>
            <p><strong>Hallucination:</strong> {'Yes' if is_hallucination else 'No'}</p>
            <p><strong>Answer:</strong> {response.answer}</p>
        </div>
"""

            html += """
    </div>
"""

        html += """
</body>
</html>
"""

        return html

    def print_summary(self):
        """Print a summary to the console."""
        summary = self._generate_summary()

        print("\n" + "=" * 80)
        print("RAG EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Video: {summary['video_title']}")
        print(f"Questions Evaluated: {summary['num_questions']}")
        print(f"SOTA Model: {summary['sota_model']}")
        print(f"Test Model: {summary['test_model']}")

        # Print timing info if available
        if self.evaluation_run.metadata.get("total_duration_seconds"):
            duration = self.evaluation_run.metadata["total_duration_seconds"]
            avg_per_question = duration / self.evaluation_run.num_questions if self.evaluation_run.num_questions > 0 else 0
            print(f"Total Duration: {duration:.1f}s ({avg_per_question:.1f}s per question)")

        # Print concurrency info if available
        if self.evaluation_run.metadata.get("max_workers"):
            mode_workers = self.evaluation_run.metadata["max_workers"]
            parallel_questions = self.evaluation_run.metadata.get("parallel_questions", False)
            question_workers = self.evaluation_run.metadata.get("question_workers", 4)
            print(f"Concurrency: {mode_workers} mode workers", end="")
            if parallel_questions:
                print(f", {question_workers} question workers (parallel)")
            else:
                print(" (sequential questions)")

        print("\n" + "-" * 80)
        print("AGGREGATE METRICS")
        print("-" * 80)

        for mode, metrics in summary['metrics'].items():
            print(f"\n{mode.upper()}:")
            print(f"  Average Overall Score: {metrics['avg_overall_score']:.1f}/100")
            print(f"  Average Accuracy: {metrics['avg_accuracy_score']:.1f}/100")
            print(f"  Hallucination Rate: {metrics['hallucination_rate']:.1f}%")
            print(f"  Average Response Time: {metrics['avg_response_time_ms']:.0f}ms")
            print(f"  Error Rate: {metrics['error_rate']:.1f}%")

        print("\n" + "-" * 80)
        print("HALLUCINATION ANALYSIS")
        print("-" * 80)

        ha = summary.get('hallucination_analysis', {})
        print(f"LLM Direct Hallucinations: {ha.get('llm_direct_count', 0)} ({ha.get('llm_direct_rate', 0):.1f}%)")
        print(f"Fast RAG Hallucinations: {ha.get('fast_rag_count', 0)} ({ha.get('fast_rag_rate', 0):.1f}%)")
        print(f"Agentic RAG Hallucinations: {ha.get('agentic_rag_count', 0)} ({ha.get('agentic_rag_rate', 0):.1f}%)")

        if 'fast_rag_reduction_pct' in ha:
            print(f"\nFast RAG Hallucination Reduction: {ha['fast_rag_reduction_pct']:.1f}%")
        if 'agentic_rag_reduction_pct' in ha:
            print(f"Agentic RAG Hallucination Reduction: {ha['agentic_rag_reduction_pct']:.1f}%")

        print("\n" + "=" * 80 + "\n")
