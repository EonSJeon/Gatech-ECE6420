"""Notebook plots from preserved measurements and actual Spectre curves only."""
import json
import re
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, Markdown
from runtime import ROOT, CURVES, FIGURES, RESULT_DIR, load_meta, require_part, execution_mode
from spectral_review import measure as coherent_measure

plt.rcParams.update({"figure.figsize": (10, 4), "axes.grid": True, "grid.alpha": .22,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def dbv(values):
    return 20*np.log10(np.maximum(np.abs(values), 1e-15))


def finish(fig, name):
    if execution_mode() == "server":
        plt.close(fig)
        raise RuntimeError("Plots must be rendered by the local notebook, not the Spectre worker.")
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def table(headers, rows):
    text = "| " + " | ".join(headers) + " |\n|" + "|".join(["---"]*len(headers)) + "|\n"
    text += "\n".join("| " + " | ".join(map(str, row)) + " |" for row in rows)
    display(Markdown(text))


def curve(name):
    path = CURVES / f"{name}.npz"
    if not path.exists():
        display(Markdown(f"**Actual curve unavailable: `{name}`.** The previous submission removed PSF data. Run the corresponding simulation notebook on the server, then pull results."))
        return None
    with np.load(path, allow_pickle=False) as data:
        current = require_part(load_meta(), name[0])["completed_utc"]
        if "part_completed_utc" not in data or str(data["part_completed_utc"]) != current:
            display(Markdown(f"**Curve `{name}` belongs to an older run.** Re-execute its simulation notebook to refresh it."))
            return None
        return {key: data[key] for key in data.files}


def ac_plot(part):
    data = curve(f"{part}_ac")
    if data is None:
        return
    fig, ax = plt.subplots()
    # b/c use 1-A output injection, so Vout is output impedance, not gain.
    ax.plot(data["frequency_Hz"]/1e9, np.abs(data["Vout"]))
    ax.set_ylabel("|Zout| (ohm), 1-A output injection")
    ax.axvline(5.8, color="C3", ls="--", label="5.8 GHz target")
    ax.set(xlabel="Frequency (GHz)", title=f"({part}) Actual AC response")
    ax.legend()
    finish(fig, f"{part}_ac")


def resonance_sweep():
    # Original terminal transcript contains real b tuning samples even though PSF was removed.
    path = ROOT / "results" / "hw5_full_terminal.txt"
    if not path.exists():
        return
    text = path.read_text(errors="replace").split("===== HW5(b) RESULT", 1)[0]
    points = re.findall(r"RES\s+W=\s*([\d.]+) um\s+L=\s*([\d.]+) nH\s+fres=\s*([\d.]+) GHz", text)
    if not points:
        return
    values = sorted({(float(l), float(f)) for _, l, f in points})
    fig, ax = plt.subplots()
    ax.plot(*zip(*values), "o-", label="Preserved terminal measurements")
    ax.axhline(5.8, color="C3", ls="--", label="5.8 GHz target")
    ax.set(xlabel="L1 (nH)", ylabel="Resonant frequency (GHz)", title="(b) Measured resonance tuning history (original run)")
    ax.legend()
    finish(fig, "b_tuning")


def matching_sweep(entry):
    points = sorted(entry["scan_points"], key=lambda p:p["W1_um"])
    w = [p["W1_um"] for p in points]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.7))
    for ax, key, label in zip(axes, ["Rin_ohm", "L1_nH", "fres_Hz"], ["Rin (ohm)", "Retuned L1 (nH)", "Resonance (GHz)"]):
        y = [p[key]/(1e9 if key=="fres_Hz" else 1) for p in points]
        ax.plot(w, y, "o-")
        ax.axvline(entry["outputs"]["W1_um"], color="C2", ls=":", label="Selected W1")
        ax.set(xlabel="W1 (um)", ylabel=label)
    axes[0].axhline(50, color="C3", ls="--", label="50 ohm target")
    axes[2].axhline(5.8, color="C3", ls="--")
    axes[0].legend(fontsize=8)
    fig.suptitle("(c) Actual coupled width / inductance search")
    finish(fig, "c_matching")


def zin_plot():
    before, after = curve("c_zin"), curve("g_zin")
    if before is None or after is None:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for data, label in [(before, "Before: dummy M2"), (after, "After: real stage 2")]:
        axes[0].plot(data["frequency_Hz"]/1e9, data["Zin"].real, label=label)
        axes[1].plot(data["frequency_Hz"]/1e9, data["Zin"].imag, label=label)
    for ax, ylabel in zip(axes, ["Re(Zin) (ohm)", "Im(Zin) (ohm)"]):
        ax.axvline(5.8, color="gray", ls=":")
        ax.set(xlabel="Frequency (GHz)", ylabel=ylabel)
        ax.legend(fontsize=8)
    finish(fig, "g_zin_comparison")


def spectrum(part, out):
    data = curve(f"{part}_tran")
    if data is None:
        # Only geometric mean amplitudes survived. Never fabricate separate tones or a noise floor.
        fundamental = out.get("Vout_fund_Vpk_geomean", out.get("Vout2_fund_Vpk_geomean"))
        im3 = out.get("Vout_IM3_Vpk_geomean", out.get("Vout2_IM3_Vpk_geomean"))
        fig, ax = plt.subplots(figsize=(6, 3.6))
        ax.scatter(["Fundamental\ngeometric mean", "IM3\ngeometric mean"], dbv([fundamental, im3]), c=["C0", "C3"], s=65)
        ax.set(ylabel="Amplitude (dBV peak)", title=f"({part}) Preserved scalar amplitudes (not a spectrum)")
        finish(fig, f"{part}_amplitudes")
        return
    t = data["time_s"]
    if np.count_nonzero((t >= 60e-9) & (t < 160e-9)) < 100:
        raise ValueError("Too few samples in coherent window")
    # Spectre can emit additional adaptive samples. Interpolate onto its known
    # 5-ps strobe grid before FFT; the metric itself retains the original method.
    grid = 60e-9 + np.arange(20000)*5e-12
    if t[0] > grid[0]+1e-15 or t[-1] < grid[-1]-1e-15:
        raise ValueError("Transient trace does not span the complete 100-ns window")
    freq = np.fft.rfftfreq(len(grid), 5e-12)
    select = (freq >= 5.70e9) & (freq <= 5.90e9)
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    source = "Vin" if part=="e" else "VinSrc"
    for ax, node in zip(axes, [source, "Vout"]):
        y = np.interp(grid, t, data[node])
        amp = 2*np.abs(np.fft.rfft(y-y.mean()))/len(y)
        markers, stems, baseline = ax.stem(
            freq[select]/1e9, np.maximum(dbv(amp[select]), -160),
            bottom=-160, linefmt="C0-", markerfmt="C0o", basefmt=" ")
        markers.set_markersize(3)
        stems.set_linewidth(1)
        for f in [5.77, 5.79, 5.81, 5.83]:
            ax.axvline(f, color="gray", alpha=.25, ls=":")
        ax.set(xlabel="Frequency (GHz)", ylabel="Amplitude (dBV peak)", title=f"({part}) {node}: actual coherent FFT")
        ax.set_ylim(-160, max(5, float(np.max(dbv(amp[select])))+8))
    finish(fig, f"{part}_spectrum")
    fig, ax = plt.subplots()
    short = (data["time_s"] >= 80e-9) & (data["time_s"] <= 82e-9)
    ax.plot(data["time_s"][short]*1e9, data["Vout"][short], label="Output")
    ax.plot(data["time_s"][short]*1e9, data[source][short], alpha=.7, label="Input source")
    ax.set(xlabel="Time (ns)", ylabel="Voltage (V)", title=f"({part}) Actual steady-state transient")
    ax.legend()
    finish(fig, f"{part}_waveform")
    compare_spectral_methods(part, out, data)


def compare_spectral_methods(part, out, data=None, show=True):
    if data is None:
        data = curve(f"{part}_tran")
    if data is None:
        return None
    current = coherent_measure(data, "Vin" if part == "e" else "VinSrc")
    legacy = out["IIP3_sim_dBV_peak"] if part == "f" else out["IIP3_dBV_peak"]
    current["legacy_IIP3_dBV_peak"] = legacy
    current["coherent_minus_legacy_IIP3_dB"] = current["IIP3_dBV_peak"]-legacy
    current["part_completed_utc"] = require_part(load_meta(), part)["completed_utc"]
    path = RESULT_DIR / "spectral_review.json"
    report = json.loads(path.read_text()) if path.exists() else {"parts": {}}
    report["note"] = "Original submission metrics are preserved. Floating-point window comparisons omit a boundary sample; the coherent check uses exactly 20000 samples. A single-point intercept still requires a cubic-region check."
    report["parts"][part] = current
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if show:
        table(["IIP3 method", "Samples", "IIP3 (dBV peak)"], [
            ["Preserved submission projection", current["legacy_selected_samples"], f"{legacy:.4f}"],
            ["Exact coherent-window check", current["coherent_samples"], f"{current['IIP3_dBV_peak']:.4f}"]])
        display(Markdown(f"The original window selected **{current['legacy_selected_samples']}** samples; the coherent check uses **20000** samples over exactly 100 ns. Coherent minus legacy IIP3: **{current['coherent_minus_legacy_IIP3_dB']:+.3f} dB**. Original submission metrics remain above. The coherent single-point estimate also needs an amplitude sweep before treating it as a validated intercept."))
    return current


def cascade_sweep(entry):
    points = sorted(entry["sweep"]["points"], key=lambda p:p["input_tone_measured_Vpk"])
    x = np.array([p["input_tone_measured_Vpk"] for p in points])
    fund = np.array([p["Vout2_fund_Vpk_geomean"] for p in points])
    im3 = np.array([p["Vout2_IM3_Vpk_geomean"] for p in points])
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    axes[0].loglog(x*1e3, fund, "o-", label="Measured fundamental")
    axes[0].loglog(x*1e3, im3, "o-", label="Measured IM3")
    axes[0].loglog(x*1e3, fund[-1]*(x/x[-1]), ":", label="Slope 1 guide")
    axes[0].loglog(x*1e3, im3[-1]*(x/x[-1])**3, ":", label="Slope 3 guide")
    axes[0].set(xlabel="Input source per tone (mVpk)", ylabel="Output (Vpk)", title="(f) Cubic-region check")
    axes[0].legend(fontsize=8)
    selected = entry["outputs"]["selected_ATONE_Vpk"]
    axes[1].plot(x*1e3, [p["IIP3_sim_dBV_peak"] for p in points], "o-", label="Simulated")
    axes[1].axhline(entry["outputs"]["IIP3_eq267_dBV_peak"], color="C3", ls="--", label="Legacy Eq. (2.67)")
    axes[1].axvline(selected*1e3, color="C2", ls=":", label="Selected amplitude")
    axes[1].set(xlabel="Input source per tone (mVpk)", ylabel="IIP3 (dBV peak)", title="Preserved sweep: IIP3 vs. drive")
    axes[1].legend(fontsize=8)
    finish(fig, "f_cubic_sweep")
    table(["Interval (mVpk)", "Fund. slope", "IM3 slope", "Score"], [
        [f"{s['low_ATONE_Vpk']*1e3:g} - {s['high_ATONE_Vpk']*1e3:g}", f"{s['fundamental_slope']:.3f}", f"{s['IM3_slope']:.3f}", f"{s['cubicity_score']:.3f}"] for s in entry["sweep"]["local_slopes"]])


def show_part(part):
    entry = require_part(load_meta(), part)
    out = entry["outputs"]
    table(["Metric", "Measured value"], [[key, f"{val:.7g}" if isinstance(val,(int,float)) else val] for key,val in out.items()])
    if part=="b":
        resonance_sweep()
        ac_plot(part)
    if part=="c":
        matching_sweep(entry)
        ac_plot(part)
    if part in "def":
        if part=="e":
            ac_plot(part)
        spectrum(part,out)
    if part=="f":
        cascade_sweep(entry)
    if part=="g":
        fig, ax = plt.subplots(figsize=(7,3.8))
        values=[out["Rin_before_second_stage_ohm"],out["Rin_after_second_stage_ohm"]]
        bars=ax.bar(["Before: dummy M2", "After: actual stage 2"],values,color=["C0","C1"])
        ax.bar_label(bars,fmt="%.2f ohm",padding=4)
        ax.axhline(50,color="C3",ls="--",label="50 ohm target")
        ax.set(ylabel="Rin at 5.8 GHz (ohm)",ylim=(0,max(values)*1.25), title="(g) Measured input resistance")
        ax.legend()
        finish(fig,"g_rin")
        zin_plot()


def show_summary():
    meta=load_meta()
    table(["Part", "Status", "Completed UTC"], [[p,meta.get("parts",{}).get(p,{}).get("status","missing"),meta.get("parts",{}).get(p,{}).get("completed_utc","-")] for p in "bcdefg"])
    if not all(meta.get("parts",{}).get(p,{}).get("status")=="complete" for p in "bcdefg"):
        display(Markdown("**Some parts are missing or stale. Execute their notebooks in dependency order.**"))
        return
    parts={p:meta["parts"][p]["outputs"] for p in "bcdefg"}
    # Source: user-provided solution PDF pages 1,3,5,8,10-13.
    rows=[
        ["(a) W1 (um), starting value",parts["b"]["W1_um"],105.94,"1"],
        ["(b) L1 (nH)",parts["b"]["L1_nH"],3.15,"3"],
        ["(c) retuned L1 (nH)",parts["c"]["L1_nH"],3.26,"5"],
        ["(d) gain (dB), source reference",parts["d"]["voltage_gain_from_Fig1_vin_source_dB"],9.98,"8"],
        ["(d) IIP3 (printed dBV)",parts["d"]["IIP3_dBV_peak"],-14.25,"8"],
        ["(e) L2 (nH)",parts["e"]["L2_nH"],3.9,"9"],
        ["(e) gain (dB)",parts["e"]["voltage_gain_dB"],6.86,"10"],
        ["(f) total gain (dB)",parts["f"]["overall_voltage_gain_dB"],18.74,"12"],
        ["(f) IIP3 (printed dBV)",parts["f"]["IIP3_sim_dBV_peak"],-18.0,"12"],
        ["(g) Rin after cascade (ohm)",parts["g"]["Rin_after_second_stage_ohm"],39.41,"13"]]
    table(["Metric", "This run", "Solution reference", "PDF page"], [[label,f"{actual:.5g}",f"{ref:g}",page] for label,actual,ref,page in rows])
    display(Markdown("**These are comparison references, not pass/fail tolerances.** The starting W1 and source amplitudes differ. The solution mixes voltage/power conventions; do not use its printed intercept numbers as an automatic correctness test."))
    spectral = [(part, compare_spectral_methods(part, parts[part], show=False)) for part in "def"]
    table(["Part", "Legacy IIP3 (dBV)", "Coherent check (dBV)", "Difference (dB)"], [
        [part, f"{check['legacy_IIP3_dBV_peak']:.3f}", f"{check['IIP3_dBV_peak']:.3f}", f"{check['coherent_minus_legacy_IIP3_dB']:+.3f}"]
        for part, check in spectral if check is not None])
    display(Markdown("**Spectral review:** the original time comparison drops a boundary sample. This creates a large IIP3 error for the weak IM3 in part (e). Legacy submission values are preserved for reproducibility; coherent checks are reported separately and still need cubic-scaling validation."))
    resonance_sweep()
    matching_sweep(meta["parts"]["c"])
    cascade_sweep(meta["parts"]["f"])
    fig, axes=plt.subplots(1,2,figsize=(10,3.8))
    axes[0].bar(["Stage 1", "Stage 2", "Sum", "Cascade"],[parts["d"]["voltage_gain_from_Fig1_vin_source_dB"],parts["e"]["voltage_gain_dB"],parts["f"]["gain_pred_from_d_plus_e_dB"],parts["f"]["overall_voltage_gain_dB"]])
    axes[0].set(ylabel="Voltage gain (dB)",title="Standalone vs. physical cascade")
    bars=axes[1].bar(["Before", "After"],[parts["g"]["Rin_before_second_stage_ohm"],parts["g"]["Rin_after_second_stage_ohm"]],color=["C0","C1"])
    axes[1].bar_label(bars,fmt="%.2f",padding=3)
    axes[1].set(ylabel="Rin (ohm)",ylim=(0,65),title="Input loading at 5.8 GHz")
    axes[1].axhline(50,color="C3",ls="--")
    finish(fig,"overview_gain_rin")
