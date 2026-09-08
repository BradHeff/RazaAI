from app.evaluation.compare import compare_summaries


def fake(model, score, hard, results, cats=None, eligible=False):
    return {
        'model':model,'score_percent':score,'hard_gate_failures':hard,
        'semantic_score_percent':score,'style_score_percent':100,'combined_score_percent':score,
        'promotion_eligible':eligible,'results':results,
        'categories':cats or {'identity':{'score_percent':score,'semantic_score_percent':score,'style_score_percent':100}},
    }

def result(case_id, passed, hard=False, category='identity', response='x'):
    return {'case_id':case_id,'passed':passed,'hard_gate':hard,'category':category,
            'response':response,'failures':[],
            'semantic_passed':passed,'semantic_failures':[] if passed else ['semantic'],
            'style_passed':True,'style_failures':[]}

def main():
    print('='*40); print('RazaAI Step 14.1 Model Comparison'); print('='*40)
    b=fake('base',90,0,[result('a',True,True),result('b',False)],eligible=True)
    c=fake('cand',95,0,[result('a',True,True),result('b',True)],eligible=True)
    r=compare_summaries(b,c)
    assert not r['semantic_regressions'] and len(r['semantic_improvements'])==1 and r['promotion_eligible']
    print('[PASS] improvement without regression can promote')
    c2=fake('cand',99,0,[result('a',False,True),result('b',True)],eligible=True)
    r2=compare_summaries(b,c2)
    assert len(r2['semantic_regressions'])==1 and r2['hard_semantic_regressions']==1 and not r2['promotion_eligible']
    print('[PASS] aggregate score cannot hide hard regression')
    b2=fake('base',90,0,[result('a',True,True),result('b',True)],eligible=True)
    c3=fake('cand',99,0,[result('a',True,True),result('b',False)],eligible=True)
    r3=compare_summaries(b2,c3)
    assert not r3['promotion_eligible']
    print('[PASS] any previously passing-case regression blocks promotion')
    print(); print('='*40); print('STEP 14.1 MODEL COMPARISON PASSED'); print('='*40)
if __name__=='__main__': main()
