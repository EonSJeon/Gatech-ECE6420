"""Validated first-stage netlist generation and AC measurements."""
import re
import math
import bisect
from runtime import REFERENCE, GENERATED, SIMULATION, F0, Q, SPECTRE, write_netlist, run_spectre as execute_spectre, find_result
SOURCE = REFERENCE / "input.scs"
WORK = GENERATED / "auto_input.scs"
RESULTS = SIMULATION / "stage1"
def run_spectre():
    return execute_spectre(WORK, RESULTS, timeout=120, preset="mx")

def fmt(x):
    """Format number cleanly for Spectre."""
    return f"{x:.12g}"

def make_netlist(w_um, l_nh, mode):
    """
    Create auto_input.scs from the original Cadence input.scs.

    mode:
        "res"
            I18 @ Vout    = AC 1 A
            I15 @ VinNode = AC 0 A

        "rin"
            I18 @ Vout    = AC 0 A
            I15 @ VinNode = AC 1 A
    """

    text = SOURCE.read_text()

    w_m = w_um * 1e-6
    l_h = l_nh * 1e-9

    # --------------------------------------------------------
    # Homework inductor model
    #
    # Q = Rp / (omega L)
    # => Rp = Q * omega0 * L
    #
    # Cp = 10 fF for every nH
    # --------------------------------------------------------

    rp = Q * 2.0 * math.pi * F0 * l_h
    cp = 10e-15 * l_nh

    # --------------------------------------------------------
    # M1 diffusion geometry
    #
    # Cadence-generated M1 at W=100um had:
    # as=ad=W*105nm
    # ps=pd=W+2*105nm
    # --------------------------------------------------------

    area = w_m * 105e-9
    perimeter = w_m + 210e-9

    # --------------------------------------------------------
    # Replace M1 statement
    # --------------------------------------------------------

    pat_m1 = (
        r"M1 \(Vout net2 VinNode 0\) NMOS_VTH .*?"
        r"(?=\nM2 )"
    )

    new_m1 = (
        "M1 (Vout net2 VinNode 0) NMOS_VTH "
        f"w={fmt(w_um)}u l=50n "
        f"as={fmt(area)} ad={fmt(area)} "
        f"ps={fmt(perimeter)} pd={fmt(perimeter)} "
        "ld=105n ls=105n m=1"
    )

    text, n = re.subn(
        pat_m1,
        new_m1 + "\n",
        text,
        flags=re.S,
    )

    if n != 1:
        raise RuntimeError(
            f"M1 replacement failed: matched {n} times"
        )

    # --------------------------------------------------------
    # Replace tank components
    # --------------------------------------------------------

    text, n = re.subn(
        r"C3 \(Vout 0\) capacitor c=\S+",
        f"C3 (Vout 0) capacitor c={fmt(cp)}",
        text,
    )
    if n != 1:
        raise RuntimeError("Could not replace C3")

    text, n = re.subn(
        r"C2 \(net2 0\) capacitor c=\S+",
        f"C2 (net2 0) capacitor c={fmt(cp)}",
        text,
    )
    if n != 1:
        raise RuntimeError("Could not replace C2")

    text, n = re.subn(
        r"L1 \(net2 Vout\) inductor l=\S+",
        f"L1 (net2 Vout) inductor l={fmt(l_h)}",
        text,
    )
    if n != 1:
        raise RuntimeError("Could not replace L1")

    text, n = re.subn(
        r"RP \(net2 Vout\) resistor r=\S+",
        f"RP (net2 Vout) resistor r={fmt(rp)}",
        text,
    )
    if n != 1:
        raise RuntimeError("Could not replace RP")

    # --------------------------------------------------------
    # Measurement mode
    # --------------------------------------------------------

    if mode == "res":
        i18 = 1
        i15 = 0

    elif mode == "rin":
        i18 = 0
        i15 = 1

    else:
        raise ValueError(
            f"Unknown measurement mode: {mode}"
        )

    text, n = re.subn(
        r"I18 \(Vout 0\) isource dc=0 type=sine mag=\S+ phase=0",
        f"I18 (Vout 0) isource dc=0 type=sine mag={i18} phase=0",
        text,
    )
    if n != 1:
        raise RuntimeError("Could not replace I18")

    text, n = re.subn(
        r"I15 \(0 VinNode\) isource dc=0 type=sine mag=\S+ phase=0",
        f"I15 (0 VinNode) isource dc=0 type=sine mag={i15} phase=0",
        text,
    )
    if n != 1:
        raise RuntimeError("Could not replace I15")

    # For output-resonance measurement, reproduce the
    # original Fig.1 input termination:
    #
    # VinNode -- 100 pF -- 50 ohm -- AC ground
    #
    # For Rin measurement, leave the input unterminated
    # because I15 itself is the 1-A test source.
    if mode == "res":
        termination = (
            "CIN_AUTO (VinNode InputTerm) capacitor c=100p\n"
            "RTERM_AUTO (InputTerm 0) resistor r=50\n"
        )

        text = text.replace(
            "I18 (Vout 0) isource",
            termination + "I18 (Vout 0) isource",
            1,
        )

    write_netlist(WORK, text)

    return rp, cp

def read_ac_ascii():
    from psf import read_ascii
    freq, traces = read_ascii(find_result(RESULTS, "ac"), "freq", ["Vout", "VinNode"], complex_values=True)
    return freq.tolist(), traces["Vout"].tolist(), traces["VinNode"].tolist()


def resonance(w_um, l_nh):

    make_netlist(
        w_um,
        l_nh,
        "res",
    )

    run_spectre()

    freq, vout, _ = read_ac_ascii()

    # Magnitude squared is sufficient for peak finding.
    power = [
        z.real * z.real + z.imag * z.imag
        for z in vout
    ]

    i = max(
        range(len(power)),
        key=power.__getitem__,
    )

    fres = freq[i]

    # --------------------------------------------------------
    # Quadratic interpolation around peak
    #
    # AC sweep resolution is ~10 MHz.
    # This estimates the true peak between grid points.
    # --------------------------------------------------------

    if 0 < i < len(freq) - 1:

        ym = power[i - 1]
        y0 = power[i]
        yp = power[i + 1]

        denominator = (
            ym
            - 2.0 * y0
            + yp
        )

        if denominator != 0.0:

            delta = (
                0.5
                * (ym - yp)
                / denominator
            )

            step = (
                freq[i + 1]
                - freq[i - 1]
            ) / 2.0

            # Avoid crazy interpolation if peak fit is bad.
            if abs(delta) <= 1.0:
                fres = (
                    freq[i]
                    + delta * step
                )

    print(
        f"RES  "
        f"W={w_um:8.3f} um  "
        f"L={l_nh:8.4f} nH  "
        f"fres={fres / 1e9:9.6f} GHz"
    )

    return fres

def rin(w_um, l_nh):

    make_netlist(
        w_um,
        l_nh,
        "rin",
    )

    run_spectre()

    freq, _, vinnode = read_ac_ascii()

    # Find points surrounding exactly 5.8 GHz.
    i = bisect.bisect_left(
        freq,
        F0,
    )

    if i <= 0:

        r = vinnode[0].real

    elif i >= len(freq):

        r = vinnode[-1].real

    else:

        f1 = freq[i - 1]
        f2 = freq[i]

        r1 = vinnode[i - 1].real
        r2 = vinnode[i].real

        alpha = (
            (F0 - f1)
            / (f2 - f1)
        )

        r = (
            r1
            + alpha * (r2 - r1)
        )

    print(
        f"RIN  "
        f"W={w_um:8.3f} um  "
        f"L={l_nh:8.4f} nH  "
        f"Rin={r:10.4f} ohm"
    )

    return r
