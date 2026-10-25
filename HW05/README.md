# HW05 - Common-gate LNA

Run the notebooks on your local computer. Spectre computes on the school Linux server through SSH; numerical results return to the local kernel, which draws the plots. FFT spectra use stem plots.

## Kernel and Run All

1. Connect GlobalProtect and confirm that `ssh gt-ece` works.
2. Open [00_overview.ipynb](notebooks/00_overview.ipynb) locally.
3. Select the **ECE6420 (Local)** kernel.
4. Run the **Run and plot** cell, or choose **Run All**, to compute all parts remotely and display results immediately in the local kernel.

The kernel is a local Python interpreter, not a remote kernel. The first setup cell prints its executable path. The registered environment currently uses Python 3.12 on this Mac. No Remote SSH extension or remote Jupyter connection is needed. Use JupyterLab, or your editor's normal local notebook support.

The kernel is already registered on this computer. To register it again, run from `HW05/`:

```bash
python3 -m pip install -r requirements.txt
python3 tools/setup_local_kernel.py
```

If using a virtual environment, activate it before those commands. Select **ECE6420 (Local)** after registering. If the name does not appear, refresh the notebook interface's kernel list.

## Notebook execution

| Notebook | Analysis | Dependencies |
|---|---|---|
| [00_overview](notebooks/00_overview.ipynb) | Run the full workflow, summary and FFT stem plots | b-g |
| [01_b](notebooks/01_b.ipynb) | L1 tuning and output resonance | Original part-(a) W1 |
| [02_c](notebooks/02_c.ipynb) | Coupled width/inductance tuning and input matching | b |
| [03_d](notebooks/03_d.ipynb) | Stage-1 two-tone gain and IIP3 | c |
| [04_e](notebooks/04_e.ipynb) | Standalone stage-2 resonance, gain and IIP3 | Independent |
| [05_f](notebooks/05_f.ipynb) | Physical cascade, amplitude sweep and Eq. (2.67) | c,d,e |
| [06_g](notebooks/06_g.ipynb) | Input impedance before and after cascading | c,e,f |

A part notebook sends the current values from its local parameter cell to the server. The worker fills missing/stale dependencies before running the requested part. Source files use the same notebook version locally and remotely; save notebook edits before running so source edits are included in synchronization. Unsaved parameter-cell values are also sent explicitly.

The default `EXECUTION_MODE` is `remote`. To redraw existing data without VPN or simulation, change the setup cell to:

```python
EXECUTION_MODE = "review"
```

Server analysis cells are skipped locally. The server worker executes those analysis cells and skips every plotting/SSH-bridge cell. It exports PSF data, compressed numerical traces, metadata and text logs. It does not produce or return plots or executed-notebook images.

## Workspace mapping and synchronization

The single maintained homework workspace is:

```text
Local:  /Users/jeonsang-eon/Gatech-ECE6420/HW05
Remote: /nethome/sjeon84/Gatech-ECE6420/HW05
```

```text
references/             Assignment and solution PDFs
netlists/reference/     Immutable Cadence input.scs and required include
netlists/generated/     Generated analysis netlists
notebooks/              One current source version of each notebook
lib/                    Shared simulation, transfer, parser and plotting functions
tools/                  Headless worker and local execution tools
results/curves/         Compressed numerical results
results/figures/        Figures created locally
simulation/             PSF, simulator logs and worker status
```

Source synchronization mirrors maintained files to the same relative paths and removes obsolete remote source files. It protects `.venv/`, numerical results, generated netlists and simulation data. Data transfer fetches numerical results and logs to their matching local paths. Local Python caches, the server virtual environment and locally rendered figures are runtime-specific artifacts, not separate project versions.

The former remote `ECE6420_HW5` Cadence project, its preclean archive and the two home-directory HW5 tar archives were deleted after the current notebook workspace was moved out. No old homework project or submission archive is retained.

Optional commands from local `HW05/`:

```bash
./tools/remote.sh status
./tools/remote.sh push --dry-run
./tools/remote.sh push
./tools/remote.sh pull
./run_all.sh
```

`./run_all.sh` performs the same local-notebook → remote-compute → local-plot workflow. It saves the locally generated output in the overview notebook. `./tools/remote.sh run --parts d` is a compute/data-transfer command; notebook cells render the plots afterward.

Override the host/path using `.remote.env`, following `tools/remote.env.example`. Authentication uses the existing `gt-ece` SSH alias. Do not place passwords or private keys in this project.

## Numerical provenance

The trusted reference netlists remain byte-identical to the original submission. The original starting width, W1 = 6.93 um, differs from the solution's 105.94 um. Preserve that distinction when comparing results with the solution PDF.

The legacy Fourier projection can omit one sample at the measurement-window boundary. Original submission metrics remain available, with a separate exact 20,000-sample / 100-ns coherent-window check. Part (e) differs by about 12.07 dB. The coherent single-point estimate still needs cubic-scaling validation. Workflow reproduction is not a certification of the legacy IIP3 method.

`results/hw5_meta.json` carries dependencies and current measurements. Rerunning an upstream part marks downstream results stale. Curve caches include their measurement timestamp. `results/migration_manifest.json` retains original hashes/baseline numbers; `results/spectral_review.json` is calculated locally from numerical data.

## Environment and verification

The worker uses the school's Spectre executable, FreePDK45 NMOS_VTH model, and verified `ece-winlic` license setting. Override them with `SPECTRE_BIN`, `HW05_MODEL` and `HW05_LICENSE`. The server Python environment is project-local; it does not change the kernel selected on the Mac.

```bash
python3 -m unittest discover -s tests -v
python3 tools/execute_notebooks.py --mode review --in-place
```

The second command redraws all saved data locally without SSH. Headless server execution writes text logs under `simulation/logs/` and status in `simulation/last_run.json`.
