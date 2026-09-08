import argparse
from app.knowledge import KnowledgeEngine

def main():
    p=argparse.ArgumentParser(); p.add_argument('query'); p.add_argument('--category'); p.add_argument('--top-k', type=int, default=5); a=p.parse_args()
    e=KnowledgeEngine()
    try:
        results=e.search(a.query, top_k=a.top_k, category=a.category)
        for i,r in enumerate(results,1):
            c=r['citation']; parts=[x for x in [c.get('title'), c.get('vendor'), c.get('product'), c.get('version'), f"page {c['page']}" if c.get('page') else None] if x]
            print(f"\n[{i}] score={r['score']} | {' | '.join(parts)}\nSource: {c.get('source')}\n{r['text']}\n")
    finally: e.close()

if __name__=='__main__': main()
