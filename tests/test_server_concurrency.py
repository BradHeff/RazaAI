"""Concurrent requests retain session state and reject malformed HTTP bodies."""

import concurrent.futures
import http.client
import json
import threading
import time
import unittest
from unittest.mock import patch

from app.server import RazaService, BoundedHTTPServer, make_handler


class CountingAgent:
    created = 0

    def __init__(self):
        type(self).created += 1
        self.turns = 0

    def ask(self, message, on_stream=None):
        time.sleep(.02)
        self.turns += 1
        return str(self.turns)


class ServiceTests(unittest.TestCase):
    def test_concurrent_same_session_uses_one_agent(self):
        CountingAgent.created = 0
        service = RazaService(CountingAgent, token='test')
        barrier = threading.Barrier(6)

        def ask(_):
            records = []
            barrier.wait()
            service.chat('shared', 'next', records.append)
            return records[-1]['content']

        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            results = list(pool.map(ask, range(6)))
        self.assertEqual(CountingAgent.created, 1)
        self.assertEqual(sorted(results), ['1', '2', '3', '4', '5', '6'])
        self.assertEqual(service.pool.describe()[0]['turns'], 6)

    def test_busy_session_cannot_be_deleted(self):
        service = RazaService(CountingAgent, token='test')
        service.pool.get('one', reserve=True)
        self.assertFalse(service.pool.drop('one'))
        service.pool.release('one')
        self.assertTrue(service.pool.drop('one'))

    def test_malformed_body_closes_connection_without_reading_it(self):
        server = BoundedHTTPServer(('127.0.0.1', 0), make_handler(RazaService(CountingAgent, token='test')))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for headers in ({'Content-Length':'1000001'}, {'Content-Length':'-1'},
                            {'Transfer-Encoding':'chunked'}, {'Content-Length':'nope'}):
                c = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                c.putrequest('POST', '/v1/chat')
                c.putheader('Authorization', 'Bearer test')
                for k, v in headers.items():
                    c.putheader(k, v)
                c.endheaders()
                response = c.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                self.assertEqual(c.sock.recv(1), b'')
                c.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_warmup_applies_profile_limits(self):
        from app.config import OLLAMA_NUM_CTX, OLLAMA_NUM_BATCH
        from app.server import warm_model
        with patch('app.ollama_client.OllamaClient.validate_memory_budget'), patch('app.server.urllib.request.urlopen') as call:
            warm_model()
            payload = json.loads(call.call_args.args[0].data)
        self.assertEqual(payload['options'], {'num_ctx': OLLAMA_NUM_CTX, 'num_batch': OLLAMA_NUM_BATCH})


if __name__ == '__main__':
    unittest.main()
