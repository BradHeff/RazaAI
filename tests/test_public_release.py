"""The source export preserves launchers and excludes private runtime files."""

from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.package_release import ignored_path, main


class ReleaseTests(unittest.TestCase):
    def test_private_paths_are_ignored(self):
        rules = Path('.gitignore').read_text().splitlines()
        for name in ('.raza-url-token', '.env.prod', 'data/memory/records.json',
                     'RazaAI_gguf_glm_v4/model.gguf', 'knowledge/networking/school-networking-field-notes.md',
                     'knowledge/project/private.md', '.local/audit.md', 'config/infrastructure.json',
                     'training/coder_v2_seed/pending.jsonl', 'requirements.lock'):
            self.assertTrue(ignored_path(name, rules), name)
        for name in ('README.md', 'app/profiles.py', 'config/infrastructure.example.json',
                     'knowledge/project/README.md', 'docs/images/interface.png'):
            self.assertFalse(ignored_path(name, rules), name)

    def test_release_files_and_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            main([temp])
            archive = next(Path(temp).glob('*.zip'))
            with zipfile.ZipFile(archive) as z:
                names = set(z.namelist())
                self.assertTrue({'LICENSE', 'README.md', 'razaai', 'razaai-8g', 'app/profiles.py'} <= names)
                self.assertFalse(any(n.startswith(('data/', '.git/', '.local/', 'logs/')) for n in names))
                self.assertNotIn('.raza-url-token', names)
                for name in ('razaai', 'razaai-8g', 'deploy.sh'):
                    self.assertTrue((z.getinfo(name).external_attr >> 16) & 0o111)


if __name__ == '__main__':
    unittest.main()
