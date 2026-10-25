"""Independent coherent-window check alongside the preserved submission method."""
import numpy as np

FREQUENCIES = np.array([5.77e9, 5.79e9, 5.81e9, 5.83e9])


def measure(data, source):
    t = np.asarray(data["time_s"])
    grid = 60e-9 + np.arange(20000)*5e-12
    if t[0] > grid[0] or t[-1] < grid[-1]:
        raise ValueError("Actual data must span the full coherent measurement grid")
    basis = np.exp(-2j*np.pi*FREQUENCIES[:, None]*grid)

    def tones(node):
        y = np.interp(grid, t, data[node])
        return np.abs(2*(basis @ (y-y.mean()))/len(grid))

    output = tones("Vout")
    input_ = tones(source)
    fund = float(np.sqrt(output[1]*output[2]))
    im3 = float(np.sqrt(output[0]*output[3]))
    ain = float(np.sqrt(input_[1]*input_[2]))
    separation = float(20*np.log10(fund/im3))
    return {"method": "20000 uniformly spaced samples; exact 100-ns coherent window; complex projection",
            "coherent_samples": len(grid),
            "legacy_selected_samples": int(np.count_nonzero((t >= 60e-9) & (t < 160e-9))),
            "fundamental_Vpk_geomean": fund, "IM3_Vpk_geomean": im3,
            "input_Vpk_geomean": ain, "gain_dB": float(20*np.log10(fund/ain)),
            "IIP3_dBV_peak": float(20*np.log10(ain)+separation/2),
            "tone_frequency_Hz": FREQUENCIES.tolist(), "output_tone_Vpk": output.tolist()}
