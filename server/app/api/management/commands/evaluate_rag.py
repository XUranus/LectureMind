"""
Django management command for running RAG evaluation.

Usage:
    python manage.py evaluate_rag --video <uuid> [options]

Examples:
    # Basic evaluation with default settings
    python manage.py evaluate_rag --video 123e4567-e89b-12d3-a456-426614174000

    # Custom number of questions and output path
    python manage.py evaluate_rag --video <uuid> --questions 30 --output ./reports/

    # Use custom models
    python manage.py evaluate_rag --video <uuid> --sota-model qwen3.6-plus --test-model qwen-turbo

    # Load existing dataset
    python manage.py evaluate_rag --video <uuid> --dataset ./my_dataset.json

    # Run with parallel question processing for faster evaluation
    python manage.py evaluate_rag --video <uuid> --parallel-questions --question-workers 4

    # Adjust concurrent RAG mode workers (default: 3)
    python manage.py evaluate_rag --video <uuid> --mode-workers 3

    # Specify custom questions (comma-separated) with total count
    python manage.py evaluate_rag --video <uuid> --question "Who are the tutors?,What is the course schedule?" --question_count 5
    # This will use 2 custom questions and generate 3 more (5-2=3)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError

from api.evaluate import RAGEvaluator, EvaluationReport
from api.evaluate.models import QuestionAnswerPair, EvaluationStatus

logger = logging.getLogger('LectureMind')


def load_dotenv_file():
    """Load .env file from project root."""
    import os
    search = Path(__file__).resolve().parent
    for _ in range(10):
        env_file = search / '.env'
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if ' #' in val:
                        val = val.split(' #')[0].strip().strip("'").strip('"')
                    if key not in os.environ:
                        os.environ[key] = val
            logger.info(f"Loaded .env from {env_file}")
            return
        search = search.parent
    logger.warning("No .env file found")


class Command(BaseCommand):
    help = "Run RAG evaluation to compare LLM Direct, Fast RAG, and Agentic RAG modes"

    def add_arguments(self, parser):
        parser.add_argument(
            '--video',
            type=str,
            required=True,
            help='UUID of the video to evaluate',
        )
        parser.add_argument(
            '--questions',
            type=int,
            default=20,
            help='Number of questions to generate (default: 20). Deprecated: use --question_count instead.',
        )
        parser.add_argument(
            '--question',
            type=str,
            help='Comma-separated list of custom questions to include in evaluation',
        )
        parser.add_argument(
            '--question_count',
            type=int,
            help='Total number of questions to evaluate. If custom questions are provided via --question, the remaining questions will be generated (N-K).',
        )
        parser.add_argument(
            '--sota-model',
            type=str,
            default='qwen3.6-plus',
            help='SOTA model for dataset generation and judging',
        )
        parser.add_argument(
            '--test-model',
            type=str,
            default='qwen-turbo',
            help='Test model for answering questions',
        )
        parser.add_argument(
            '--output',
            type=str,
            default='./evaluation_reports',
            help='Output directory for reports',
        )
        parser.add_argument(
            '--dataset',
            type=str,
            help='Path to existing dataset JSON file (optional)',
        )
        parser.add_argument(
            '--save-dataset',
            action='store_true',
            help='Save the generated dataset to the output directory',
        )
        parser.add_argument(
            '--formats',
            type=str,
            default='json,md,html',
            help='Comma-separated list of output formats: json,csv,md,html',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging',
        )
        parser.add_argument(
            '--mode-workers',
            type=int,
            default=3,
            help='Number of concurrent workers for RAG modes (default: 3)',
        )
        parser.add_argument(
            '--parallel-questions',
            action='store_true',
            help='Process questions in parallel (default: sequential)',
        )
        parser.add_argument(
            '--question-workers',
            type=int,
            default=4,
            help='Number of concurrent workers for parallel question processing (default: 4)',
        )
        parser.add_argument(
            '--no-irrelevant',
            action='store_true',
            help='Disable generation of irrelevant questions (default: 30%% of questions are irrelevant for hallucination detection)',
        )
        parser.add_argument(
            '--irrelevant-ratio',
            type=float,
            default=0.3,
            help='Ratio of irrelevant questions for hallucination detection (default: 0.3 = 30%%)',
        )

    def handle(self, *args, **options):
        # Load environment variables
        load_dotenv_file()

        # Set up logging
        if options['verbose']:
            logging.getLogger('LectureMind').setLevel(logging.DEBUG)

        video_id = options['video']
        sota_model = options['sota_model']
        test_model = options['test_model']
        output_dir = Path(options['output'])
        dataset_path = options['dataset']
        save_dataset = options['save_dataset']
        formats = [f.strip() for f in options['formats'].split(',')]
        mode_workers = options['mode_workers']
        parallel_questions = options['parallel_questions']
        question_workers = options['question_workers']

        # Parse custom questions if provided
        custom_questions = []
        if options['question']:
            custom_questions = [q.strip() for q in options['question'].split(',') if q.strip()]

        # Determine total question count
        # Priority: --question_count > --questions (deprecated) > default (20)
        if options['question_count'] is not None:
            total_questions = options['question_count']
        elif options['questions'] != 20:  # User specified --questions
            total_questions = options['questions']
        else:
            total_questions = 20

        # Validate: total questions must be >= custom questions
        if custom_questions and total_questions < len(custom_questions):
            raise CommandError(
                f"--question_count ({total_questions}) must be >= number of custom questions "
                f"({len(custom_questions)}). Either increase --question_count or provide fewer custom questions."
            )

        # Calculate how many questions to generate
        num_to_generate = total_questions - len(custom_questions) if custom_questions else total_questions

        self.stdout.write(self.style.SUCCESS(f"Starting RAG Evaluation for video {video_id}"))
        self.stdout.write(f"SOTA Model: {sota_model}")
        self.stdout.write(f"Test Model: {test_model}")
        self.stdout.write(f"Total Questions: {total_questions}")
        if custom_questions:
            self.stdout.write(f"Custom Questions: {len(custom_questions)}")
            for i, q in enumerate(custom_questions, 1):
                self.stdout.write(f"  {i}. {q}")
        self.stdout.write(f"Questions to Generate: {num_to_generate}")
        self.stdout.write(f"Mode Workers: {mode_workers}")
        self.stdout.write(f"Parallel Questions: {parallel_questions}")
        if parallel_questions:
            self.stdout.write(f"Question Workers: {question_workers}")
        self.stdout.write("")

        # Validate video exists
        from api.models import Video
        try:
            video = Video.objects.get(id=video_id)
            self.stdout.write(f"Video: {video.title}")
        except Video.DoesNotExist:
            raise CommandError(f"Video with ID {video_id} not found")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load or generate dataset
        qa_pairs = None
        if dataset_path:
            self.stdout.write(f"Loading dataset from {dataset_path}...")
            qa_pairs = self._load_dataset(dataset_path)
            if qa_pairs:
                self.stdout.write(self.style.SUCCESS(f"Loaded {len(qa_pairs)} Q&A pairs"))
            else:
                self.stdout.write(self.style.WARNING("Failed to load dataset, will generate new one"))

        # Create custom Q&A pairs from manual questions
        custom_qa_pairs = []
        if custom_questions:
            self.stdout.write("Creating custom Q&A pairs from manual questions...")
            custom_qa_pairs = self._create_custom_qa_pairs(custom_questions, video_id, sota_model)
            self.stdout.write(self.style.SUCCESS(f"Created {len(custom_qa_pairs)} custom Q&A pairs"))

        # Initialize evaluator
        try:
            evaluator = RAGEvaluator(
                video_id=video_id,
                sota_model=sota_model,
                test_model=test_model,
                max_workers=mode_workers,
                parallel_questions=parallel_questions,
                question_workers=question_workers,
                include_irrelevant_questions=not options['no_irrelevant'],
                irrelevant_ratio=options['irrelevant_ratio'],
            )
        except ValueError as e:
            raise CommandError(str(e))

        # Merge custom and loaded/generated qa_pairs
        # Priority: custom_qa_pairs > loaded qa_pairs > generated
        final_qa_pairs = None
        if custom_qa_pairs and qa_pairs:
            # Both custom and loaded - merge them
            final_qa_pairs = custom_qa_pairs + qa_pairs
            # Limit to total_questions if specified
            if len(final_qa_pairs) > total_questions:
                final_qa_pairs = final_qa_pairs[:total_questions]
        elif custom_qa_pairs:
            # Only custom questions - will generate remaining
            final_qa_pairs = custom_qa_pairs
        elif qa_pairs:
            # Only loaded questions
            final_qa_pairs = qa_pairs

        # Run evaluation
        self.stdout.write("\nRunning evaluation...")
        self.stdout.write("This may take several minutes depending on the number of questions.")
        self.stdout.write("")

        try:
            evaluation_run = evaluator.run_evaluation(
                num_questions=num_to_generate,
                qa_pairs=final_qa_pairs,
            )
        except Exception as e:
            logger.exception("Evaluation failed")
            raise CommandError(f"Evaluation failed: {e}")

        # Check status
        if evaluation_run.status == EvaluationStatus.FAILED:
            error_msg = evaluation_run.metadata.get('error', 'Unknown error')
            raise CommandError(f"Evaluation failed: {error_msg}")

        self.stdout.write(self.style.SUCCESS("Evaluation completed successfully!"))
        self.stdout.write("")

        # Save dataset if requested
        if save_dataset and not dataset_path:
            dataset_file = output_dir / f"dataset_{video_id}_{evaluation_run.id}.json"
            self._save_dataset(evaluation_run.question_results, dataset_file)
            self.stdout.write(f"Dataset saved to: {dataset_file}")

        # Generate reports
        report = EvaluationReport(evaluation_run)

        # Print summary to console
        report.print_summary()

        # Save reports in requested formats
        saved_files = []
        base_filename = f"rag_eval_{video_id}_{evaluation_run.id}"

        for fmt in formats:
            try:
                if fmt == 'json':
                    filepath = output_dir / f"{base_filename}.json"
                    report.save(str(filepath), format='json')
                    saved_files.append(filepath)
                elif fmt == 'csv':
                    filepath = output_dir / f"{base_filename}.csv"
                    report.save(str(filepath), format='csv')
                    saved_files.append(filepath)
                elif fmt in ('md', 'markdown'):
                    filepath = output_dir / f"{base_filename}.md"
                    report.save(str(filepath), format='md')
                    saved_files.append(filepath)
                elif fmt == 'html':
                    filepath = output_dir / f"{base_filename}.html"
                    report.save(str(filepath), format='html')
                    saved_files.append(filepath)
                else:
                    self.stdout.write(self.style.WARNING(f"Unknown format: {fmt}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to save {fmt} report: {e}"))

        # Print saved files
        if saved_files:
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write("REPORTS SAVED")
            self.stdout.write("=" * 80)
            for filepath in saved_files:
                self.stdout.write(f"  - {filepath}")
            self.stdout.write("")

        # Generate comparison analysis
        self.stdout.write("Generating comparative analysis...")
        comparison = evaluator.compare_modes(evaluation_run)

        # Save comparison as JSON
        comparison_file = output_dir / f"{base_filename}_comparison.json"
        with open(comparison_file, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        self.stdout.write(f"Comparison analysis saved to: {comparison_file}")

        self.stdout.write(self.style.SUCCESS("\nEvaluation complete!"))

    def _load_dataset(self, dataset_path: str) -> Optional[list]:
        """Load Q&A pairs from a JSON file."""
        try:
            path = Path(dataset_path)
            if not path.exists():
                self.stdout.write(self.style.ERROR(f"Dataset file not found: {dataset_path}"))
                return None

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle different JSON structures
            if isinstance(data, list):
                qa_data = data
            elif isinstance(data, dict) and 'qa_pairs' in data:
                qa_data = data['qa_pairs']
            else:
                self.stdout.write(self.style.ERROR("Invalid dataset format"))
                return None

            qa_pairs = []
            for item in qa_data:
                qa_pair = QuestionAnswerPair(
                    question=item.get('question', ''),
                    ground_truth_answer=item.get('ground_truth_answer', item.get('answer', '')),
                    question_type=item.get('question_type', 'factual'),
                    difficulty=item.get('difficulty', 'medium'),
                    source_knowledge_ids=item.get('source_knowledge_ids', []),
                    metadata=item.get('metadata', {}),
                )
                qa_pairs.append(qa_pair)

            return qa_pairs

        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"Invalid JSON in dataset file: {e}"))
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to load dataset: {e}"))
            return None

    def _save_dataset(self, question_results: list, filepath: Path):
        """Save Q&A pairs to a JSON file."""
        qa_pairs = [qr.qa_pair.to_dict() for qr in question_results]

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({"qa_pairs": qa_pairs}, f, indent=2, ensure_ascii=False)

    def _create_custom_qa_pairs(
        self, questions: list, video_id: str, sota_model: str
    ) -> list:
        """
        Create QuestionAnswerPair objects from manual questions.
        Uses SOTA model to generate ground truth answers from comprehensive knowledge base
        including slides, transcripts, and knowledge points.
        """
        from api.evaluate.models import QuestionAnswerPair
        from api.llm_client import get_llm_client
        from api.models import KnowledgeSummary, KnowledgePoint, VideoSection, SlideOCR, TranscriptSentence

        qa_pairs = []

        # Gather comprehensive context from knowledge base
        context_parts = []

        # Get knowledge summary
        try:
            summary = KnowledgeSummary.objects.get(video_id=video_id)
            context_parts.append(f"Lecture Overview: {summary.overview}")
            context_parts.append(f"Key Topics: {', '.join(summary.key_topics)}")
            if summary.learning_objectives:
                context_parts.append(f"Learning Objectives: {', '.join(summary.learning_objectives)}")
        except KnowledgeSummary.DoesNotExist:
            pass

        # Get slide OCR content - crucial for tutor/contact info
        slide_ocrs = SlideOCR.objects.filter(video_id=video_id).order_by('time_second')
        if slide_ocrs.exists():
            context_parts.append("\n=== SLIDE CONTENT (OCR) ===")
            for slide in slide_ocrs[:15]:  # Include more slides for comprehensive context
                time_str = f"{int(slide.time_second // 60):02d}:{int(slide.time_second % 60):02d}"
                context_parts.append(f"\n[Slide at {time_str}]:\n{slide.ocr_text[:800]}")

        # Get knowledge points
        knowledge_points = KnowledgePoint.objects.filter(video_id=video_id)
        if knowledge_points.exists():
            context_parts.append("\n=== KNOWLEDGE POINTS ===")
            for kp in knowledge_points[:10]:
                context_parts.append(f"- {kp.title}: {kp.summary}")

        # Get section titles with transcripts
        sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
        if sections.exists():
            context_parts.append("\n=== LECTURE SECTIONS ===")
            for s in sections[:5]:
                time_range = f"{int(s.begin_time // 60):02d}:{int(s.begin_time % 60):02d} - {int(s.end_time // 60):02d}:{int(s.end_time % 60):02d}"
                context_parts.append(f"- [{time_range}] {s.title}")
                if s.transcript_text:
                    context_parts.append(f"  Transcript: {s.transcript_text[:300]}...")

        context = "\n".join(context_parts) if context_parts else "No knowledge base available."

        # Use SOTA model to generate answers for each question
        llm = get_llm_client(model=sota_model)

        for i, question in enumerate(questions, 1):
            self.stdout.write(f"  Generating answer for question {i}/{len(questions)}: {question[:50]}...")

            prompt = f"""You are an expert evaluator creating ground truth answers for RAG evaluation.
Based on the following comprehensive lecture knowledge base (including slides, transcripts, and knowledge points), answer the question accurately.

## Knowledge Base:
{context[:12000]}  # Limit context to avoid token limits

## Question:
{question}

## Instructions:
1. Provide a comprehensive, accurate answer based ONLY on the knowledge base above
2. If the answer is found in slides, cite the approximate timestamp
3. If the knowledge base doesn't contain sufficient information, clearly state: "INSUFFICIENT_INFO: [explain what's missing]"
4. Be precise with names, emails, dates, and other factual information
5. If multiple pieces of information exist, include all relevant details

Ground Truth Answer:"""

            try:
                answer = llm.chat(
                    prompt=prompt,
                    system_prompt="You are an expert teaching assistant with access to lecture slides, transcripts, and knowledge points. Provide accurate, comprehensive answers based on the provided context.",
                    temperature=0.2,  # Lower temperature for more factual answers
                    max_tokens=2048,
                )

                # Check if answer indicates insufficient info
                is_answerable = not answer.strip().startswith("INSUFFICIENT_INFO")

                qa_pair = QuestionAnswerPair(
                    question=question,
                    ground_truth_answer=answer.strip(),
                    question_type="custom",
                    difficulty="medium",
                    source_knowledge_ids=[],
                    metadata={
                        "source": "manual",
                        "index": i,
                        "is_answerable_from_kb": is_answerable,
                    },
                )
                qa_pairs.append(qa_pair)

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed to generate answer for '{question}': {e}"))
                # Create with empty answer as fallback
                qa_pair = QuestionAnswerPair(
                    question=question,
                    ground_truth_answer="[Failed to generate ground truth answer]",
                    question_type="custom",
                    difficulty="medium",
                    source_knowledge_ids=[],
                    metadata={"source": "manual", "index": i, "error": str(e)},
                )
                qa_pairs.append(qa_pair)

        return qa_pairs
