"""Physical cascade construction and shared two-tone measurements."""
import re
import math
import cmath
from runtime import *
BASE = ROOT
WORK = GENERATED / "f_cascade.scs"
RESULTS = SIMULATION / "f"
RS = 50.0
F1, F2 = 5.79e9, 5.81e9
IM31, IM32 = 2*F1-F2, 2*F2-F1
ATONE = 2.5e-3
TSTOP, WINDOW_START = 160e-9, 60e-9
MAXSTEP, STROBE = 3e-12, 5e-12
def run_spectre():
    return __import__("runtime").run_spectre(WORK, RESULTS)

def build_netlist(w1_um, l1_nh, l2_nh, rp2_ohm, cp2_ff):
    import tune_c

    tune_c.SPECTRE = SPECTRE

    # Generate the validated first-stage circuit from part (c).
    # "rin" mode has no 50-ohm termination; we add the real
    # two-tone source below.
    tune_c.make_netlist(
        w1_um,
        l1_nh,
        "rin",
    )

    src = tune_c.WORK

    if not src.exists():
        raise RuntimeError(
            "tune_c.make_netlist() did not create auto_input.scs"
        )

    text = src.read_text()

    # Remove the original dummy M2 from Fig.1.
    text, n = re.subn(
        r"^M2 \(net2 Vout 0 0\) NMOS_VTH .*?(?=^V0 )",
        "",
        text,
        count=1,
        flags=re.M | re.S,
    )

    if n != 1:
        raise RuntimeError(
            f"Could not remove original Fig.1 dummy M2; matches={n}"
        )

    # Remove tune_c AC test sources.
    text = re.sub(
        r"^I18 .*?\n",
        "",
        text,
        flags=re.M,
    )

    text = re.sub(
        r"^I15 .*?\n",
        "",
        text,
        flags=re.M,
    )

    # Replace the old AC/DC analyses by a nonlinear transient test.
    if "simulatorOptions options" not in text:
        raise RuntimeError(
            "Could not locate simulatorOptions in generated first-stage netlist"
        )

    prefix = text.split(
        "simulatorOptions options",
        1,
    )[0]

    cp2 = cp2_ff * 1e-15
    l2 = l2_nh * 1e-9

    second_stage = f'''
// ===========================================================
// Fig.3 second stage replacing the dummy M2 of Fig.1
// ===========================================================

M5 (Vout2 Vout S2 0) NMOS_VTH w=5u l=50n \\
    as=9.45e-15 ad=9.45e-15 ps=300n pd=300n \\
    ld=105n ls=105n m=1

IB2 (S2 0) isource dc=1.5m
CS2 (S2 0) capacitor c=100f

L2   (net2 Vout2) inductor l={l2:.12g}
RP2  (net2 Vout2) resistor r={rp2_ohm:.12g}
CP2A (net2 0) capacitor c={cp2:.12g}
CP2B (Vout2 0) capacitor c={cp2:.12g}
CLOAD2 (Vout2 0) capacitor c=150f

// ===========================================================
// Two-tone source for the whole cascade
// ===========================================================

VT1 (tone1 0) vsource type=sine dc=0 ampl={ATONE:.12g} freq={F1:.12g}
VT2 (VinSrc tone1) vsource type=sine dc=0 ampl={ATONE:.12g} freq={F2:.12g}

RSRC (VinSrc VinPre) resistor r={RS:.12g}
CIN_F (VinPre VinNode) capacitor c=100p

// ===========================================================
// Nonlinear transient simulation
// ===========================================================

simulatorOptions options temp=27 tnom=27 gmin=1e-12 reltol=1e-4

tran tran stop={TSTOP:.12g} maxstep={MAXSTEP:.12g} \\
    strobeperiod={STROBE:.12g}

save Vout2 Vout VinNode VinSrc S2
saveOptions options save=allpub
'''

    write_netlist(WORK, 
        prefix + second_stage
    )

def read_tran():
    from psf import read_ascii
    names = ["Vout2", "Vout", "VinNode", "VinSrc"]
    t, traces = read_ascii(find_result(RESULTS, "tran"), "time", names)
    if len(t) < 100:
        raise ValueError("Not enough transient samples")
    return (t.tolist(), *(traces[name].tolist() for name in names))


def tone_amp(t, y, f):
    pts = [
        (ti, yi)
        for ti, yi in zip(t, y)
        if WINDOW_START <= ti < TSTOP
    ]

    if len(pts) < 100:
        raise RuntimeError(
            "Not enough samples in Fourier measurement window"
        )

    mean = (
        sum(
            yi
            for _, yi in pts
        )
        / len(pts)
    )

    w = (
        2.0
        * math.pi
        * f
    )

    z = sum(
        (yi - mean)
        * cmath.exp(
            -1j * w * ti
        )
        for ti, yi in pts
    )

    return (
        2.0
        * abs(z)
        / len(pts)
    )

def gmean(a, b):
    return math.sqrt(
        max(a, 1e-300)
        * max(b, 1e-300)
    )

def eq267_prediction(dout, eout):
    # Eq. (2.67), voltage convention:
    #
    # 1/A_IP3,total^2
    #   ~= 1/A_IP3,1^2 + alpha1^2/A_IP3,2^2
    #
    # alpha1 = first-stage voltage gain.

    aip3_1 = float(
        dout["IIP3_Vpk"]
    )

    aip3_2 = float(
        eout["IIP3_Vpk"]
    )

    g1_db = float(
        dout[
            "voltage_gain_from_Fig1_vin_source_dB"
        ]
    )

    alpha1 = (
        10.0
        ** (g1_db / 20.0)
    )

    aip3_total = (
        1.0
        / math.sqrt(
            1.0 / (aip3_1 * aip3_1)
            + (alpha1 * alpha1)
            / (aip3_2 * aip3_2)
        )
    )

    return (
        aip3_total,
        alpha1,
    )
