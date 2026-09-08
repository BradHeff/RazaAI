import argparse
from app.knowledge import KnowledgeEngine

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--force', action='store_true'); args=parser.parse_args()
    engine=KnowledgeEngine()
    try:
        result=engine.ingest_all(force=args.force)
        print('\n========================================\nRazaAI Knowledge Ingestion\n========================================\n')
        for item in result['documents']:
            print(f"[{item['status'].upper():9}] {item['source']} ({item['chunks']} chunks)")
        for source in result['removed']: print(f"[REMOVED  ] {source}")
        print(f"\nVector points: {engine.collection_count()}\n")
    finally: engine.close()

if __name__=='__main__': main()
