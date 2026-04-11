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
            help='Number of questions to generate (default: 20)',
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

    def handle(self, *args, **options):
        # Load environment variables
        load_dotenv_file()

        # Set up logging
        if options['verbose']:
            logging.getLogger('LectureMind').setLevel(logging.DEBUG)

        video_id = options['video']
        num_questions = options['questions']
        sota_model = options['sota_model']
        test_model = options['test_model']
        output_dir = Path(options['output'])
        dataset_path = options['dataset']
        save_dataset = options['save_dataset']
        formats = [f.strip() for f in options['formats'].split(',')]
        mode_workers = options['mode_workers']
        parallel_questions = options['parallel_questions']
        question_workers = options['question_workers']

        self.stdout.write(self.style.SUCCESS(f"Starting RAG Evaluation for video {video_id}"))
        self.stdout.write(f"SOTA Model: {sota_model}")
        self.stdout.write(f"Test Model: {test_model}")
        self.stdout.write(f"Number of Questions: {num_questions}")
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

        # Initialize evaluator
        try:
            evaluator = RAGEvaluator(
                video_id=video_id,
                sota_model=sota_model,
                test_model=test_model,
                max_workers=mode_workers,
                parallel_questions=parallel_questions,
                question_workers=question_workers,
            )
        except ValueError as e:
            raise CommandError(str(e))

        # Run evaluation
        self.stdout.write("\nRunning evaluation...")
        self.stdout.write("This may take several minutes depending on the number of questions.")
        self.stdout.write("")

        try:
            evaluation_run = evaluator.run_evaluation(
                num_questions=num_questions,
                qa_pairs=qa_pairs,
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
