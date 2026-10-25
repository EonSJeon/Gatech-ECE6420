"""Regression checks for the migrated circuit builders and notebook workflow."""
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import numpy as np
import runtime
import tune_c
import hw5_f
from psf import read_ascii
from spectral_review import measure as coherent_measure


def notebook_helpers(filename):
    nb = json.loads((ROOT / "notebooks" / filename).read_text())
    namespace = dict(vars(runtime))
    # Parameter and helper cells define the actual notebook API without running Spectre.
    exec("".join(nb["cells"][3]["source"]), namespace)
    exec("".join(nb["cells"][5]["source"]), namespace)
    return namespace


class WorkflowTests(unittest.TestCase):
    def test_coherent_review_handles_floating_point_window_boundary(self):
        nominal = np.arange(32001)*5e-12
        t = nominal + (nominal-100e-9)*1e-12
        signal = lambda f: np.sin(2*np.pi*f*t)
        source = .02*(signal(5.79e9)+signal(5.81e9))
        output = .1*(signal(5.79e9)+signal(5.81e9)) + .0001*(signal(5.77e9)+signal(5.83e9))
        measured = coherent_measure({"time_s": t, "VinSrc": source, "Vout": output}, "VinSrc")
        self.assertEqual(measured["legacy_selected_samples"], 19999)
        self.assertEqual(measured["coherent_samples"], 20000)
        self.assertAlmostEqual(measured["fundamental_Vpk_geomean"], .1, places=8)
        self.assertAlmostEqual(measured["IM3_Vpk_geomean"], .0001, places=8)
        self.assertAlmostEqual(measured["IIP3_dBV_peak"], 20*math.log10(.02*math.sqrt(.1/.0001)), places=6)


    def test_login_license_does_not_override_verified_project_license(self):
        spec = importlib.util.spec_from_file_location("isolated_runtime", ROOT / "lib" / "runtime.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"CDS_LIC_FILE": "5280@ece-linlic.ece.gatech.edu", "HW05_LICENSE": ""}):
            os.environ.pop("HW05_LICENSE")
            spec.loader.exec_module(module)
        self.assertIn("ece-winlic.ece.gatech.edu", module.LICENSE)

    def test_reference_is_byte_identical(self):
        manifest = json.loads((ROOT / "results" / "migration_manifest.json").read_text())
        for name in ("input.scs", "ade_e.scs"):
            self.assertEqual(runtime.sha256(runtime.REFERENCE / name), manifest["original_sha256"][name])

    def test_measurement_topology_and_component_units(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "auto.scs"
            with patch.object(tune_c, "WORK", deck):
                rp, cp = tune_c.make_netlist(50, 5.7, "res")
                res = deck.read_text()
                tune_c.make_netlist(50, 5.7, "rin")
                rin = deck.read_text()
            self.assertIn("RTERM_AUTO (InputTerm 0) resistor r=50", res)
            self.assertNotIn("RTERM_AUTO", rin)
            self.assertIn("I15 (0 VinNode) isource dc=0 type=sine mag=1", rin)
            self.assertIn("I18 (Vout 0) isource dc=0 type=sine mag=0", rin)
            self.assertAlmostEqual(rp, 8*2*math.pi*5.8e9*5.7e-9)
            self.assertAlmostEqual(cp/1e-15, 57)

    def test_cascade_and_input_impedance_testbench(self):
        g = notebook_helpers("06_g.ipynb")
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            with patch.object(tune_c, "WORK", d / "auto.scs"), patch.object(hw5_f, "WORK", d / "cascade.scs"):
                hw5_f.build_netlist(50, 5.7, 3.8, 1108, 38)
                cascade = hw5_f.WORK.read_text()
                self.assertNotIn("M2 (net2 Vout", cascade)
                self.assertIn("M5 (Vout2 Vout S2 0)", cascade)
                self.assertIn("RSRC (VinSrc VinPre) resistor r=50", cascade)
                g["WORK"] = d / "zin.scs"
                g["build_g_netlist"](50, 5.7, 3.8, 1108, 38)
                zin = g["WORK"].read_text()
                self.assertIn("M5 (Vout2 Vout S2 0)", zin)
                self.assertIn("ITEST_G (0 VinNode)", zin)
                self.assertNotIn("RSRC (", zin)
                self.assertNotIn("VT1 (", zin)
                self.assertNotIn("tran tran", zin)

    def test_second_stage_bias_and_test_setups(self):
        e = notebook_helpers("04_e.ipynb")
        with tempfile.TemporaryDirectory() as directory:
            e["WORK"] = Path(directory) / "e.scs"
            e["write_ac"](3.8)
            ac = e["WORK"].read_text()
            self.assertIn("VG  (Vin 0) vsource dc=1 mag=0", ac)
            self.assertIn("ITEST (Vout 0)", ac)
            e["write_tran"](3.8)
            tran = e["WORK"].read_text()
            self.assertIn("VBIAS (vbias 0) vsource dc=1", tran)
            self.assertIn("ampl=0.01", tran)
            self.assertIn("IB  (S 0) isource dc=1.5m", tran)

    def test_upstream_rerun_invalidates_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta.json"
            base = {"parts": {p: {"status": "complete", "completed_utc": "original", "outputs": {}} for p in "bcdefg"}}
            path.write_text(json.dumps(base))
            with patch.object(runtime, "META", path), patch.object(runtime, "RESULT_DIR", Path(directory)):
                changed = copy.deepcopy(base)
                changed["parts"]["b"]["completed_utc"] = "rerun"
                runtime.save_meta(changed)
                saved = runtime.load_meta()
                for p in "cdfg":
                    self.assertEqual(saved["parts"][p]["status"], "stale")
                self.assertEqual(saved["parts"]["e"]["status"], "complete")
                with self.assertRaises(RuntimeError):
                    runtime.require_part(saved, "f")

    def test_psfascii_discovery_and_strict_trace_lengths(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            p = d / "ac.ac.ac"
            p.write_text('HEADER\nVALUE\n"freq" 5e9\n"VinNode" (50, 3)\n"freq" 6e9\n"VinNode" (51, -2)\nEND\n')
            self.assertEqual(runtime.find_result(d, "ac"), p)
            x, traces = read_ascii(p, "freq", ["VinNode"], complex_values=True)
            np.testing.assert_equal(x, [5e9, 6e9])
            np.testing.assert_equal(traces["VinNode"], [50+3j, 51-2j])
            p.write_text(p.read_text().replace('"VinNode" (51, -2)\n', ''))
            with self.assertRaises(ValueError):
                read_ascii(p, "freq", ["VinNode"], complex_values=True)

    def test_coherent_tone_projection(self):
        # Independent constructed signal: 579/581/577 whole cycles in 100 ns.
        t = 60e-9 + np.arange(20000)*5e-12
        y = 1.2 + .02*np.sin(2*np.pi*5.79e9*t) + .01*np.cos(2*np.pi*5.81e9*t) + .0002*np.sin(2*np.pi*5.77e9*t)
        self.assertAlmostEqual(hw5_f.tone_amp(t, y, 5.79e9), .02, places=10)
        self.assertAlmostEqual(hw5_f.tone_amp(t, y, 5.77e9), .0002, places=10)

    def test_original_intercept_and_inductor_arithmetic(self):
        baseline = json.loads((ROOT / "results" / "migration_manifest.json").read_text())["baseline_outputs"]
        for part in "bce":
            out = baseline[part]
            l = out["L2_nH"] if part == "e" else out["L1_nH"]
            self.assertAlmostEqual(out["Rp_ohm"], 8*2*math.pi*5.8*l, places=7)
            self.assertAlmostEqual(out["Cp_each_fF"], 10*l, places=7)
        expected = 20e-3*math.sqrt(baseline["d"]["Vout_fund_Vpk_geomean"]/baseline["d"]["Vout_IM3_Vpk_geomean"])
        # Original projection measures 20.001 mV instead of the nominal 20 mV.
        self.assertAlmostEqual(baseline["d"]["IIP3_Vpk"], expected, delta=2e-5)


if __name__ == "__main__":
    unittest.main()
