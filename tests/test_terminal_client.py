"""The lightweight client rejects incomplete streams and displays revised answers."""

import contextlib
import io
import runpy
import unittest
from unittest.mock import patch


class ClientTests(unittest.TestCase):
    def ask(self, records):
        client = runpy.run_path('bin/raza', run_name='test_client')
        response = io.BytesIO(records)
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(client['ask'].__globals__, {'_request': lambda *a, **k: response}), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = client['ask']('hello')
        self.assertTrue(response.closed)
        return status, output.getvalue(), errors.getvalue()

    def test_incomplete_and_invalid_streams_fail(self):
        for data in (b'{"delta":"partial"}\n', b'not json\n', b'{"error":"runner failed"}\n'):
            status, _, errors = self.ask(data)
            self.assertEqual(status, 1)
            self.assertIn('error:', errors)

    def test_revised_answer_is_visible(self):
        status, output, errors = self.ask(b'{"delta":"draft"}\n{"done":true,"content":"corrected answer"}')
        self.assertEqual(status, 0)
        self.assertEqual(errors, '')
        self.assertIn('Final answer:\ncorrected answer', output)


if __name__ == '__main__':
    unittest.main()
