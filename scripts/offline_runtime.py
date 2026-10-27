"""Import the unchanged staged modules with fake credentials and no .env read.

Only for local export/fixture checks; never configures a live extraction run.
"""
from contextlib import contextmanager, ExitStack
import importlib
import os
from unittest.mock import patch


@contextmanager
def no_network():
    with ExitStack() as stack:
        for target in ('socket.socket.connect', 'socket.socket.connect_ex',
                       'socket.create_connection', 'urllib.request.urlopen'):
            stack.enter_context(patch(target, side_effect=RuntimeError('Network disabled for offline checks')))
        yield


def load_staged(name='pipeline'):
    placeholders = {'DEEPSEEK_API_KEY': 'offline-fixture-only',
                    'DEEPSEEK_BASE_URL': 'http://127.0.0.1:9',
                    'DEEPSEEK_MODEL': 'synthetic-fixture'}
    with patch.dict(os.environ, placeholders), patch('dotenv.load_dotenv', return_value=False), no_network():
        return importlib.import_module(name)
