"""Profile selection, request limits and launcher portability."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def run_profile(self, profile, **overrides):
        env = {k: v for k, v in os.environ.items() if not k.startswith('RAZAAI_')}
        env.update(overrides)
        return subprocess.run([str(ROOT / profile), 'config'], cwd='/tmp', env=env,
                              capture_output=True, text=True)

    def test_launchers_are_independent(self):
        standard = self.run_profile('razaai')
        edge = self.run_profile('razaai-8g')
        self.assertEqual(standard.returncode, 0, standard.stderr)
        self.assertEqual(edge.returncode, 0, edge.stderr)
        a, b = json.loads(standard.stdout), json.loads(edge.stdout)
        self.assertEqual((a['context'], a['batch']), (16384, 512))
        self.assertEqual((b['context'], b['batch']), (4096, 128))
        for key in ['state', 'model', 'code_model', 'port']:
            self.assertNotEqual(a[key], b[key])

    def test_terminal_is_default_and_web_is_workstation_only(self):
        import types
        from unittest.mock import Mock, patch
        from app.launcher import main

        for profile in ('standard', '8g'):
            terminal = Mock()
            with patch.dict(sys.modules, {'app.main': types.SimpleNamespace(main=terminal)}), patch.dict(os.environ, {}, clear=False):
                main(['--profile', profile])
                terminal.assert_called_once_with([])
                terminal.reset_mock()
                main(['--profile', profile, 'code', '/tmp/example-project'])
                terminal.assert_called_once_with(['--workspace', '/tmp/example-project'])
        result = subprocess.run([str(ROOT / 'razaai-8g'), 'web'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(self.run_profile('razaai-8g').stdout)
        self.assertEqual(data['interface'], 'terminal')
        self.assertFalse(data['web_available'])
        self.assertIsNone(data['port'])

    def test_edge_rejects_unsafe_context(self):
        for value in ('-1', '0', 'bad', '32768'):
            result = self.run_profile('razaai-8g', RAZAAI_OLLAMA_NUM_CTX=value)
            self.assertNotEqual(result.returncode, 0)
        result = self.run_profile('razaai-8g', RAZAAI_OLLAMA_NUM_BATCH='512')
        self.assertNotEqual(result.returncode, 0)

    def test_explicit_model_override(self):
        result = self.run_profile('razaai', RAZAAI_CODE_MODEL='my-coder:q4', RAZAAI_OLLAMA_MODEL='my-chat:q4')
        data = json.loads(result.stdout)
        self.assertEqual(data['code_model'], 'my-coder:q4')
        self.assertEqual(data['model'], 'my-chat:q4')

    def test_model_setup_uses_profile_definitions_without_checkout_templates(self):
        from unittest.mock import patch
        from app.launcher import setup_models
        from app.profiles import PROFILES

        for profile in PROFILES.values():
            definitions = {}

            def run(command, **kwargs):
                if command[1] == 'create':
                    definitions[command[2]] = Path(command[-1]).read_text()
                return subprocess.CompletedProcess(command, 0)

            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / 'local model.gguf'
                source.write_bytes(b'GGUF-test')
                with patch('app.launcher.subprocess.run', side_effect=run):
                    setup_models(profile, str(source))
                chat = definitions[profile.model]
                coder = definitions[profile.code_model]
                self.assertIn(f'FROM {json.dumps(str(source))}', chat)
                self.assertIn(f'FROM {profile.code_base}', coder)
                for definition in (chat, coder):
                    self.assertIn(f'num_ctx {profile.context}', definition)
                    self.assertIn(f'num_batch {profile.batch}', definition)
                    self.assertIn('created by Brad Heffernan', definition)
                self.assertIn('Never claim a test passed without supplied evidence', coder)
            with self.assertRaises(ValueError):
                profile.modelfile('example\nPARAMETER num_ctx 99999')

    def test_profile_install_does_not_reuse_foreign_lock(self):
        text = (ROOT / 'deploy.sh').read_text()
        self.assertIn('pip install -r requirements.txt', text)
        self.assertNotIn('pip install -r requirements.lock', text)
        self.assertNotIn('source .env', text)


class ModelBudgetTests(unittest.TestCase):
    def test_edge_models_must_fit_the_profile(self):
        from unittest.mock import patch
        from app.ollama_client import OllamaClient, OllamaError
        from app.profiles import PROFILES

        client = OllamaClient()
        with patch('app.ollama_client.PROFILE', PROFILES['8g']):
            for count, quant, accepted in (
                (4_000_000_000, 'Q4_K_M', True),
                (7_000_000_000, 'Q4_K_M', False),
                (4_000_000_000, 'F16', False),
                (None, '', False),
            ):
                info = {'model_info': {'general.parameter_count': count},
                        'details': {'quantization_level': quant}}
                with self.subTest(count=count, quant=quant), patch.object(client, 'model_info', return_value=info), patch('urllib.request.urlopen') as generate:
                    if accepted:
                        client.validate_memory_budget()
                    else:
                        with self.assertRaises(OllamaError):
                            client.chat([{'role': 'user', 'content': 'hi'}])
                    generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
