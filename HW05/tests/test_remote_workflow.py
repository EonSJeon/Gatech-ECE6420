"""Checks for local execution, data-only transfer and headless server notebooks."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import nbformat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import remote_bridge as bridge
import runtime


class RemoteWorkflowTests(unittest.TestCase):
    def test_local_default_and_server_role(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime.execution_mode(), "remote")
            self.assertFalse(runtime.simulation_enabled())
        with patch.dict(os.environ, {"HW05_EXECUTION_MODE": "server"}):
            self.assertTrue(runtime.simulation_enabled())

    def test_local_parameters_are_sent_as_data(self):
        config = bridge.RemoteConfig()
        parameters = {"d": {"ATONE": .007, "F1": 5.79e9}}
        with patch.object(bridge.RemoteConfig, "load", return_value=config), patch.object(bridge, "push_sources") as push, patch.object(bridge, "pull_data") as pull, patch.object(bridge, "run_command") as execute:
            bridge.run_remote_parts("d", parameters)
        push.assert_called_once_with(config)
        pull.assert_called_once_with(config)
        command, payload = execute.call_args.args
        self.assertEqual(json.loads(payload), parameters)
        self.assertIn("tools/remote_worker.py --parts d", command[-1])

    def test_data_transfer_never_fetches_images_or_notebook_outputs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bridge, "ROOT", Path(directory)), patch.object(bridge, "rsync") as rsync:
            bridge.pull_data(bridge.RemoteConfig())
            calls = rsync.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("/notebooks/" not in call.args[1] for call in calls))
        self.assertIn("figures/", calls[0].kwargs["excludes"])
        self.assertIn("executed/", calls[2].kwargs["excludes"])

    def test_source_mirror_protects_runtime_and_server_results(self):
        with patch.object(bridge, "run_command"), patch.object(bridge, "rsync") as rsync:
            bridge.push_sources(bridge.RemoteConfig())
        mirror = rsync.call_args_list[0]
        self.assertTrue(mirror.kwargs["delete"])
        self.assertIn("/results/", mirror.kwargs["excludes"])
        self.assertIn("/simulation/", mirror.kwargs["excludes"])
        self.assertTrue(all(c.kwargs["ignore_existing"] for c in rsync.call_args_list[1:]))

    def test_headless_worker_skips_plot_and_bridge_cells(self):
        spec = importlib.util.spec_from_file_location("execute_test", ROOT / "tools" / "execute_notebooks.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            path = d / "test.ipynb"
            nb = nbformat.v4.new_notebook(cells=[
                nbformat.v4.new_code_cell("ATONE = .01", metadata={"tags": ["parameters"]}),
                nbformat.v4.new_code_cell("run_remote_parts('d')", metadata={"tags": ["remote-bridge"]}),
                nbformat.v4.new_code_cell("spectrum('d')", metadata={"tags": ["local-only"]}),
                nbformat.v4.new_code_cell("print('compute')", metadata={"tags": ["server-analysis"]})])
            nb.metadata["hw05"] = {"parameters": ["ATONE"]}
            nbformat.write(nb, path)
            before = path.read_bytes()
            class Client:
                def __init__(self, notebook, **kwargs): self.notebook = notebook
                def create_kernel_manager(self): return SimpleNamespace(kernel_spec=SimpleNamespace(argv=[]))
                def execute(self): pass
            with patch.object(module, "ROOT", d), patch.object(module, "NotebookClient", Client), patch.dict(os.environ):
                result = module.execute_path(path, "server", {"ATONE": .007})
            skipped = [c for c in result.cells if "skip-execution" in c.metadata.get("tags", [])]
            self.assertEqual(len(skipped), 2)
            self.assertIn("0.007", result.cells[1].source)
            self.assertEqual(before, path.read_bytes())
            self.assertFalse(list(d.rglob("*.png")))
            self.assertTrue((d / "simulation/logs/test.log").exists())

    def test_remote_path_rejects_wrong_scope(self):
        for invalid in ["/", "/nethome/sjeon84", "/nethome/sjeon84/../HW05"]:
            with patch.dict(os.environ, {"HW05_REMOTE_DIR": invalid}):
                with self.assertRaises(ValueError): bridge.RemoteConfig.load()


if __name__ == "__main__":
    unittest.main()
