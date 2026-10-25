# ECE6420 - Wireless IC Design

Georgia Tech ECE6420 circuit-simulation homework and projects. The course covers RF nonlinearity/noise, receivers, LNAs, mixers, VCOs and PLLs. See the [course syllabus](course/ECE6420_Syllabus_2026%20Fall.pdf).

The current assignment is [HW05: Common-gate LNA](HW05/README.md).

Open [HW05/notebooks/00_overview.ipynb](HW05/notebooks/00_overview.ipynb), select **ECE6420 (Local)**, connect GlobalProtect, and choose **Run All**. Computation runs through SSH on the school server; received numerical data is plotted in the local kernel. FFT plots use stems. No remote notebook kernel or Remote SSH extension is required.

```text
course/                 Course syllabus
HW05/
  references/           Assignment and solution PDFs
  netlists/reference/   Immutable reference netlists
  netlists/generated/   Generated netlists
  notebooks/            Current notebook source
  lib/                  Shared computation, transfer and plotting functions
  results/              Numerical results and locally rendered figures
  simulation/           PSF, logs and worker status
  tools/                Execution and synchronization tools
```

The local and remote homework roots correspond directly:

```text
Local:  Gatech-ECE6420/HW05
Remote: /nethome/sjeon84/Gatech-ECE6420/HW05
```

The named local kernel is already registered on this Mac. See [HW05 setup and execution](HW05/README.md) for registration commands, parameter editing and offline review mode. The [common prompt](Common%20Prompt%20%E2%80%94%20ECE%20Circuit%20Simulation%20Homework%20with%20Cadence_Spectre.md) records conventions for later assignments.
