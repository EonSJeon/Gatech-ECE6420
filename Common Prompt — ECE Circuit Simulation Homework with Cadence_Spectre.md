# Common Prompt - ECE6420 Circuit Simulation with Cadence/Spectre

Follow the assignment PDF and the user's current instructions. This repository contains Georgia Tech ECE6420 simulation homework and projects. See the syllabus under `course/` for course context. Write all documentation, notebook text, code comments and run messages in English.

## Intended workflow

Use a local notebook as the user interface:

```text
Local Run / Run All
    -> mirror source to the school server over SSH/rsync
    -> execute Spectre and analysis cells remotely, without plotting
    -> fetch numerical data, generated netlists and logs
    -> compute/render plots in the local notebook kernel
```

Do not render plots remotely and import their PNGs or executed-notebook outputs. Plot FFT spectra with stems. Use real simulation traces; never fabricate missing curves or noise floors.

The user is a Cadence beginner. Prefer code-driven simulation over Virtuoso/ADE interaction. Explain any unavoidable GUI action from first principles.

## Local kernel

Select **ECE6420 (Local)** in the local notebook interface. It is a local Python kernel, not a remote kernel. The notebook setup cell prints the interpreter path. SSH sends computation to the server independently of the selected local kernel.

The local kernel is registered using:

```bash
cd HW05
python3 -m pip install -r requirements.txt
python3 tools/setup_local_kernel.py
```

No Remote SSH extension or remote Jupyter connection is required. JupyterLab or normal local notebook support is sufficient. Default mode is `remote`; use `EXECUTION_MODE = "review"` to redraw saved numerical data without VPN.

## Server access and project mapping

Connect GlobalProtect, then confirm `ssh gt-ece` works. Use the existing SSH alias/key; do not silently alter `~/.ssh/config`.

```text
SSH alias: gt-ece
Configured host: ece-linlabsrv01.ece.gatech.edu
Server-reported hostname: ece-labsrv
Home: /nethome/sjeon84
Local root: Gatech-ECE6420/HW05
Remote root: /nethome/sjeon84/Gatech-ECE6420/HW05
Spectre: /tools/software/cadence/spectre/latest/tools.lnx86/bin/spectre
Model: /tools/designkits/NCSU/FreePDK4514/ncsu_basekit/models/hspice/tran_models/models_nom/NMOS_VTH.inc
Device: NMOS_VTH
Server Python: /usr/bin/python3, Python 3.9
```

The server may use tcsh. Use an explicit Bash command for Bash syntax.

The verified project license is:

```text
5280@ece-winlic.ece.gatech.edu:1055@ansyslic.ecs.gatech.edu
```

The worker sets both `CDS_LIC_FILE` and `LM_LICENSE_FILE` to this value. The login environment historically points to `ece-linlic` and can fail. Use `HW05_LICENSE` for an explicit project override. Diagnose failures from the actual Spectre log; do not speculate about license availability.

## File organization

Wrap assignments as `HW01/`, `HW02/`, etc. Keep one maintained notebook project, with matching relative source/data paths locally and remotely.

```text
HWxx/
  references/            Assignment, solution and reference PDFs
  netlists/reference/    Trusted immutable input.scs and required includes
  netlists/generated/    Derived analysis netlists
  notebooks/             Summary and per-part notebooks
  lib/                   Shared simulation, transfer, parser and plotting helpers
  results/curves/        Compact numerical traces
  results/figures/       Locally rendered figures
  simulation/            PSF, logs and worker status
  tools/                 Local execution and headless server worker
```

Keep netlists separate from simulator output. Resolve paths from file locations rather than relying on the current working directory. Preserve the original trusted `input.scs`; generate derived netlists instead of modifying it.

The old remote Cadence HW5 project and its homework archives were removed at the user's request. Do not reintroduce full_submission folders, old project copies or submission archives. Project-local virtual environments/caches are runtime artifacts, not separate source versions.

## Source and data transfer

Use SSH/rsync rather than terminal copy/paste when available. The local notebook's current parameter-cell values are sent explicitly as JSON, so unsaved parameter values affect the requested simulation. Save source edits so edited code is mirrored as well.

Source push mirrors the maintained source and removes obsolete remote source files. Protect numerical results, generated netlists, simulation data, `.venv` and credentials from source cleanup. Data pull transfers numerical results and logs only; it never replaces the local notebook's code or imports remote plots.

```bash
./tools/remote.sh status
./tools/remote.sh push --dry-run
./tools/remote.sh push
./tools/remote.sh pull
./run_all.sh
```

`./run_all.sh` runs the local overview notebook, delegates computation to the server, and saves locally generated outputs. The server worker skips every plotting/SSH-bridge cell and writes text logs, not a second executed-notebook version.

## Circuit and testbench correctness

- Trace drain/gate/source/body connections against the assignment figure and trusted netlist before automating sweeps.
- Preserve PDK callback geometry unless evidence shows it is wrong.
- Keep the original source termination for output-resonance tests. HW05 uses `VinNode - 100 pF - 50 ohm - AC ground`.
- For input impedance, remove the external 50-ohm source branch and inject 1 A AC into the input. Then `Zin = Vin / 1 A`; report real/imaginary parts and magnitude.
- For the HW05 inductor model, update linked values together: `Rp = Q*2*pi*f0*L`, each `Cp = 10 fF/nH`.
- Retune L for each width candidate when matching Rin and resonance simultaneously.
- A cascade simulation must replace the dummy load with the actual next stage. Compare its gain/IIP3 with standalone-stage predictions separately.
- Finite output resistance and parasitic feedback can make drain loading affect input impedance. Measure the actual cascade.
- Keep ideal hand-calculation assumptions such as lambda = 0 distinct from the PDK simulation model.

## Measurements and provenance

Use shared metadata with status, inputs, outputs, dependency names, upstream values and completion timestamps. Missing/stale dependencies must be computed or rejected explicitly, never replaced with hard-coded defaults. Rerunning an upstream part marks dependent results stale. Numerical curve caches must identify the matching measurement timestamp.

Use `-format psfascii`, check Spectre's return code and log, and discover actual filenames such as `ac*.ac` and `tran*.tran`. Parse only the VALUE section and validate trace lengths, finite values and axis order. Distinguish simulator failure from parser/path failure.

HW05 tones are 5.79/5.81 GHz; IM3 tones are 5.77/5.83 GHz. Label Vpk, Vrms, Vpp, source voltage, internal input voltage and available power carefully.

```text
Delta_dB = 20*log10(Afund/Aim3)
IIP3_dBV = input_dBV + Delta_dB/2
Thevenin available input power per tone = Vopen-circuit,pk^2/(8*Rs)
```

A floating-point `start <= t < stop` test can omit a boundary sample. Use an exact coherent grid derived from the interval and strobe spacing, verify trace coverage, and compare legacy and corrected-window results explicitly. Sweep input amplitude to check fundamental slope near 1 and IM3 slope near 3. Do not select a point merely because its intercept agrees with theory.

The original HW05 W1 = 6.93 um differs from the solution's 105.94 um. The solution mixes some voltage/power conventions. Preserve these distinctions; do not force the circuit to match a printed answer. Legacy IIP3 values and independent coherent-window checks are separate results, and a single-point intercept still requires cubic-scaling validation.

## Completion checks

Verify trusted-netlist hashes, measurement topology, dependency handling, parameter transfer, headless server execution and local rendering. Run the notebooks locally through the actual SSH/data path. Check that the server creates no plot files, FFTs use stems, source paths correspond one to one, and old homework copies have not reappeared. State the notebook to open and the exact local kernel name.
