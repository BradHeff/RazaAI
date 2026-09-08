from app.knowledge import KnowledgeEngine
from app.tools.registry import ToolRegistry
TEST_QUERY='What VLAN does the fictional RazaAI Atlas lab use for out-of-band management?'

def main():
    print('\n========================================\nRazaAI Step 5 Knowledge Quality Test\n========================================\n')
    e=KnowledgeEngine()
    try:
        first=e.ingest_all(); second=e.ingest_all()
        if [x for x in second['documents'] if x['status']=='indexed']:
            raise AssertionError('Incremental ingestion re-indexed unchanged documents')
        results=e.search(TEST_QUERY, top_k=5, category='networking')
        match=next((x for x in results if 'VLAN 845' in x['text']), None)
        if not match: raise AssertionError('Expected VLAN 845 knowledge was not retrieved')
        c=match['citation']
        if c.get('title')!='RazaAI Atlas Laboratory Network Standard': raise AssertionError('Title metadata missing')
        if c.get('vendor')!='RazaAI Labs': raise AssertionError('Vendor metadata missing')
        print('[PASS] incremental ingestion skips unchanged documents')
        print('[PASS] semantic retrieval found VLAN 845')
        print('[PASS] citation metadata preserved')
    finally: e.close()
    r=ToolRegistry().execute('search_knowledge', {'query':TEST_QUERY,'category':'networking','top_k':5})
    if not r.success or not r.result['results']: raise AssertionError(f'Tool failed: {r.error}')
    print('[PASS] search_knowledge tool integration')
    print('\n========================================\nSTEP 5 KNOWLEDGE QUALITY PASSED\n========================================\n')

if __name__=='__main__': main()
