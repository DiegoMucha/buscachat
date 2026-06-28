#!/usr/bin/env python3
"""Genera embeddings faciales para los registros sincronizados de SOS Venezuela.

Uso:
    cd buscachat-python
    uv run python scripts/generate_embeddings.py --max 20
"""

import argparse
import logging
import sys
from pathlib import Path

# Asegurar que el proyecto esté en sys.path
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from app.services.embedding_sync import generate_embeddings_for_synced_records

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate face embeddings for synced records")
    parser.add_argument("--max", type=int, default=50, help="Max records to process")
    args = parser.parse_args()

    result = generate_embeddings_for_synced_records(max_records=args.max)

    print(f"\nResultado:")
    print(f"  Procesados: {result['processed']}")
    print(f"  Exitosos:   {result['successes']}")
    print(f"  Fallidos:   {result['failures']}")
    print(f"  Saltados:   {result['skipped']}")


if __name__ == "__main__":
    main()
