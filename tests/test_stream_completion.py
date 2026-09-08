"""Incomplete and failed model streams never become successful answers."""

import io
import json
import unittest
from unittest.mock import patch

from app.ollama_client import OllamaClient, OllamaError


class StreamTests(unittest.TestCase):
    def response(self, records):
        return io.BytesIO(b''.join(json.dumps(r).encode() + b'\n' for r in records))

    def test_incomplete_stream_fails(self):
        client = OllamaClient()
        with patch.object(client, 'validate_memory_budget'), patch.object(client, '_think_field', return_value={}), patch('urllib.request.urlopen', return_value=self.response([{'message':{'content':'partial'}}])):
            with self.assertRaisesRegex(OllamaError, 'before the answer completed'):
                client.chat_stream([{'role':'user','content':'hi'}])

    def test_error_record_fails(self):
        client = OllamaClient()
        with patch.object(client, 'validate_memory_budget'), patch.object(client, '_think_field', return_value={}), patch('urllib.request.urlopen', return_value=self.response([{'error':'runner failed'}])):
            with self.assertRaisesRegex(OllamaError, 'runner failed'):
                client.chat_stream([{'role':'user','content':'hi'}])

    def test_literal_marker_prefix_is_preserved(self):
        client = OllamaClient()
        records = [{'message':{'content':'a <'}}, {'done':True}]
        pieces = []
        with patch.object(client, 'validate_memory_budget'), patch.object(client, '_think_field', return_value={}), patch('urllib.request.urlopen', return_value=self.response(records)):
            result = client.chat_stream([{'role':'user','content':'hi'}], on_chunk=pieces.append)
        self.assertEqual(result['message']['content'], 'a <')
        self.assertEqual(''.join(pieces), 'a <')


if __name__ == '__main__':
    unittest.main()
