"""Persona reaches both profiles without disabling reasoning or changing permissions."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.agent.agent import core_identity_for
from app.coding.coworker import WorkspaceCoworker
from app.ollama_client import OllamaClient
from app.personality import CODING_PERSONA, RAZAAI_MISSION, security_personality_lead
from app.profiles import PROFILES
from app.tools.workspace import WorkspaceManager


class PersonaTests(unittest.TestCase):
    def test_same_mission_in_both_profiles(self):
        for profile in PROFILES.values():
            for tag in (profile.model, profile.code_model):
                identity = core_identity_for(tag, full_voice=True)
                self.assertIn(RAZAAI_MISSION, identity)
                self.assertIn('Think independently', identity)
                self.assertIn('required approvals', profile.modelfile(profile.base_model))
        self.assertLess(len(core_identity_for('razaai-8g', full_voice=True)), 3500)

    def test_identity_explains_loyalty_and_principles(self):
        from app.conversation_coherence import self_identity_authoritative_response
        answer = self_identity_authoritative_response('Who are you?', identity_context_active=False)
        for phrase in ("Halo's Cortana", 'ride or die', 'best interests', 'disagreeing',
                       'honesty, evidence', 'facts change'):
            self.assertIn(phrase, answer)
        self.assertEqual(self_identity_authoritative_response('What is your name?',
                                                             identity_context_active=False), 'RazaAI.')

    def test_coding_plans_and_repairs_receive_the_mission(self):
        captured = []

        class Client:
            def chat(self, messages, **kwargs):
                captured.append(messages)
                return {'message': {'content': '{"files":[],"summary":"Inspect before changing"}'}}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'calc.py'
            source.write_text('def add(a, b):\n    return a + b\n')
            manager = WorkspaceManager(root)
            coworker = WorkspaceCoworker(client=Client(), manager=manager, require_approval=True)
            listing = manager.list_files(recursive=True)
            coworker._planner('Review calc.py for correctness', listing, coworker._project_profile(listing))
            coworker._repair('Fix calc.py', ['calc.py'], [], 1)
            for messages in captured:
                self.assertIn(CODING_PERSONA, messages[0]['content'])
                self.assertIn('Return JSON only', messages[0]['content'])
            self.assertEqual(len(captured), 2)
            self.assertEqual(source.read_text(), 'def add(a, b):\n    return a + b\n')

    def test_questions_do_not_receive_automatic_insults(self):
        for question in ('Is a text file safe for passwords?', 'What about Excel?', 'What is a password manager?'):
            self.assertEqual(security_personality_lead(question), '')
        self.assertTrue(security_personality_lead('I store passwords in a text file'))

    def test_native_thinking_is_an_independent_operator_choice(self):
        client = OllamaClient()
        with patch.dict(os.environ, {}, clear=True), patch.object(client, 'capabilities', return_value={'thinking'}):
            self.assertEqual(client._think_field(), {})
            for value, expected in [('auto', {}), ('1', {'think': True}), ('off', {'think': False}), ('high', {'think': 'high'})]:
                os.environ['RAZAAI_THINK'] = value
                self.assertEqual(client._think_field(), expected)
            os.environ['RAZAAI_THINK'] = 'invalid'
            with self.assertRaises(ValueError):
                client._think_field()
        with patch.dict(os.environ, RAZAAI_THINK='1'), patch.object(client, 'capabilities', return_value={'completion'}):
            self.assertEqual(client._think_field(), {})

    def test_thinking_stream_remains_separate_from_the_answer(self):
        client = OllamaClient()
        records = [{'message': {'thinking': 'Checking the evidence.'}},
                   {'message': {'content': 'The answer is 42.'}}, {'done': True}]
        response = io.BytesIO(b''.join(json.dumps(r).encode() + b'\n' for r in records))
        thinking, answer = [], []
        with patch.dict(os.environ, RAZAAI_THINK='auto'), patch.object(client, 'validate_memory_budget'), patch('urllib.request.urlopen', return_value=response):
            result = client.chat_stream([{'role': 'user', 'content': 'Check this.'}],
                                        on_chunk=answer.append, on_thinking=thinking.append)
        self.assertEqual(''.join(thinking), 'Checking the evidence.')
        self.assertEqual(''.join(answer), 'The answer is 42.')
        self.assertEqual(result['message']['content'], 'The answer is 42.')


if __name__ == '__main__':
    unittest.main()
