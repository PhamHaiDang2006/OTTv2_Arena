import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from ottv2_runner.engine_verifier import EngineBuildVerifier
from ottv2_runner.sandbox import DockerSandbox


class BuildResourcesTests(unittest.TestCase):
    def test_smoke_uses_configured_build_cpus_and_closes_bot(self):
        sandbox = Mock()
        sandbox.start_bot.return_value.close = AsyncMock()
        result = SimpleNamespace(reason='GOAL', winner='RED')
        with patch.dict(os.environ, {'RUNNER_CPUSET_BUILD': '6-7'}), \
                patch('ottv2_runner.engine_verifier.run_game', new=AsyncMock(return_value=result)):
            EngineBuildVerifier(sandbox).verify('image', {'engine_version': '1.0.0', 'submission_id': 'test'})
        sandbox.start_bot.assert_called_once_with('image', '6-7')
        sandbox.start_bot.return_value.close.assert_awaited_once()

    def test_compiler_pinned_with_existing_limits_and_cleanup(self):
        client = Mock()
        container = client.containers.create.return_value
        container.wait.return_value = {'StatusCode': 0}
        container.logs.return_value = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'RUNNER_CPUSET_BUILD': '6-7'}):
            source = Path(tmp) / 'source'
            source.mkdir()
            sandbox = DockerSandbox(client, specs={'cpp': None})
            sandbox._compile(SimpleNamespace(language='cpp', builder_image='compiler'), source)
        options = client.containers.create.call_args.kwargs
        self.assertEqual(options['cpuset_cpus'], '6-7')
        self.assertEqual(options['nano_cpus'], 1_000_000_000)
        self.assertEqual(options['mem_limit'], '512m')
        self.assertEqual(options['memswap_limit'], '512m')
        self.assertEqual(options['network_mode'], 'none')
        container.remove.assert_called_once_with(force=True)
