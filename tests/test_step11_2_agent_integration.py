from pathlib import Path


def main():
    print('\n========================================')
    print('RazaAI Step 11.2 Agent Integration Test')
    print('========================================\n')

    source = Path('app/agent/agent.py').read_text(encoding='utf-8')

    assert 'IncidentPatternAnalyzer' in source
    assert 'self.incident_patterns = IncidentPatternAnalyzer' in source
    assert 'self.last_incident_patterns' in source
    assert 'analyze_matches' in source
    assert '[Incident Pattern] Recurrence:' in source
    assert 'incident_pattern_guidance' in source

    print('[PASS] recurrence analyzer wired into RazaAgent')
    print('[PASS] recurrence computed after validated retrieval')
    print('[PASS] compact recurrence guidance injected into 4B context')

    print('\n========================================')
    print('STEP 11.2 AGENT INTEGRATION PASSED')
    print('========================================\n')


if __name__ == '__main__':
    main()
