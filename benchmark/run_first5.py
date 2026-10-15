import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_core import build_parser, parse_questions, run_benchmark  

FIRST_N = 5


def main() -> int:
    parser = build_parser(
        "Бенчмарк: первые 5 запросов из docs/request_examples.txt",
        default_json="benchmark/results_first6.json",
    )
    args = parser.parse_args()

    questions = parse_questions(Path(args.file))[:FIRST_N]
    print(f"Загружено вопросов: {len(questions)} (первые {FIRST_N}) из {args.file}")
    print(f"API: {args.base_url} | top_k={args.top_k} | mode={args.mode} | "
          f"tolerance={args.tolerance}%")
    print()

    return run_benchmark(
        questions,
        base_url=args.base_url,
        api_key=args.api_key,
        top_k=args.top_k,
        tolerance=args.tolerance,
        timeout=args.timeout,
        mode=args.mode,
        json_out=Path(args.json) if args.json else None,
    )


if __name__ == "__main__":
    sys.exit(main())