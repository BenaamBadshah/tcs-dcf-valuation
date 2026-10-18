import yfinance as yf

# --- Stage 1: establish the market anchor ---
# The DCF will produce an INTRINSIC value from TCS's own cash flows.
# To call the stock over- or under-valued we compare that to the live
# market price. This price is the ONLY number we let the internet give us.

TICKER = "TCS.NS"        # TCS on the NSE; ".NS" tells yfinance it's India's NSE

stock = yf.Ticker(TICKER)
fi = stock.fast_info      # fast_info is the reliable, lightweight data path

price       = fi.last_price      # current market price per share (₹)
market_cap  = fi.market_cap      # total equity value the market assigns (₹)
shares_out  = market_cap / price # implied share count (market_cap = price × shares)

print(f"Ticker:             {TICKER}")
print(f"Live price:         ₹{price:,.2f}")
print(f"Market cap:         ₹{market_cap/1e7:,.0f} crore")
print(f"Implied shares:     {shares_out/1e7:,.2f} crore shares")

import pandas as pd
import matplotlib.pyplot as plt

# --- Stage 2: historical revenue, EBIT & operating margin ---
# Screener's "Operating Profit" is EBITDA (pre-depreciation), so real EBIT =
# Operating Profit - Depreciation. We need EBIT because the firm-level DCF
# discounts operating profit available to ALL investors, before financing.

# INPUT SECTION — from TCS consolidated P&L on Screener.in (₹ crore).
data = {
    "FY":      [2021,   2022,   2023,   2024,   2025,   2026],
    "Revenue": [164177, 191754, 225458, 240893, 255324, 267021],  # Sales
    "EBITDA":  [46546,  53057,  59259,  64296,  67407,  72398],    # "Operating Profit"
    "Deprec":  [4065,   4604,   5022,   4985,   5242,   5560],     # Depreciation
}

df = pd.DataFrame(data)

# CALCULATIONS
df["EBIT"]          = df["EBITDA"] - df["Deprec"]          # true operating profit
df["Rev_growth_%"]  = df["Revenue"].pct_change() * 100     # YoY revenue growth
df["EBIT_margin_%"] = df["EBIT"] / df["Revenue"] * 100     # operating margin

print(df.round(2).to_string(index=False))

# VISUAL — revenue bars (growth) + EBIT margin line (stability)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

ax1.bar(df["FY"], df["Revenue"], color="#4C72B0")
ax1.set_title("Revenue (₹ crore)")
ax1.set_xlabel("FY")

ax2.plot(df["FY"], df["EBIT_margin_%"], marker="o", color="#C44E52")
ax2.set_title("EBIT margin (%)")
ax2.set_xlabel("FY")
ax2.set_ylim(0, 30)   # fix axis at 0 so the line's flatness is honest, not zoomed

plt.tight_layout()
plt.show()

# --- Stage 3: historical free cash flow to the firm (FCFF) ---
# FCFF = EBIT*(1-tax) + Depreciation - CapEx + WC_change
# This is the cash the WHOLE business generates before any financing — the
# exact thing we'll discount at WACC in the valuation step.

# NEW INPUTS (₹ crore): Tax % from the P&L; CapEx & WC change from the Cash Flow stmt.
df["Tax_rate"]  = [0.26, 0.26, 0.26, 0.26, 0.25, 0.24]        # effective tax %
df["CapEx"]     = [3176, 2995, 3100, 2674, 3937, 4146]        # "Fixed assets purchased"
df["WC_change"] = [863, -2769, -4217, -6882, -3359, -2210]    # as reported on CFS
# NOTE ON SIGN: the CFS already signs WC as a cash effect (negative = cash used
# up as the business grows). So we ADD this column as-is; we do NOT subtract it.

# CALCULATIONS
df["NOPAT"] = df["EBIT"] * (1 - df["Tax_rate"])               # after-tax operating profit
df["FCFF"]  = df["NOPAT"] + df["Deprec"] - df["CapEx"] + df["WC_change"]

# quality check: how much operating profit actually becomes cash
df["FCF_conversion_%"] = df["FCFF"] / df["NOPAT"] * 100

cols = ["FY", "EBIT", "Tax_rate", "NOPAT", "Deprec", "CapEx", "WC_change",
        "FCFF", "FCF_conversion_%"]
print(df[cols].round(2).to_string(index=False))

# VISUAL — the FCFF series
plt.figure(figsize=(7, 4))
plt.bar(df["FY"], df["FCFF"], color="#55A868")
plt.title("Free Cash Flow to the Firm (₹ crore)")
plt.xlabel("FY")
plt.tight_layout()
plt.show()

# --- Stage 4: forecast FCFF for the explicit period (5 years) ---
# Only ONE new assumption here: the growth rate. It's isolated and labelled
# because this is the number you must defend. Everything else flows from Stage 3.

g_explicit     = 0.06          # <-- YOUR assumption: explicit-period FCFF growth
forecast_years = 5

last_fcff = df["FCFF"].iloc[-1]        # FY2026 actual FCFF = base for the projection
last_year = int(df["FY"].iloc[-1])     # 2026

# project: each future year = base * (1 + g)^n
future_fy   = [last_year + n for n in range(1, forecast_years + 1)]
future_fcff = [last_fcff * (1 + g_explicit) ** n for n in range(1, forecast_years + 1)]

fc = pd.DataFrame({"FY": future_fy, "FCFF": future_fcff})

print(f"Base FCFF (FY{last_year}): ₹{last_fcff:,.0f} cr   |   growth: {g_explicit:.1%}")
print(fc.round(0).to_string(index=False))

# VISUAL — actual (green) vs forecast (amber, hatched)
plt.figure(figsize=(9, 4))
plt.bar(df["FY"], df["FCFF"], color="#55A868", label="Actual")
plt.bar(fc["FY"], fc["FCFF"], color="#DD8452", hatch="//", label="Forecast")
plt.title("FCFF: historical vs forecast (₹ crore)")
plt.xlabel("FY")
plt.legend()
plt.tight_layout()
plt.show()

# --- Stage 5a: estimate TCS's beta by regression against the Nifty 50 ---
# Beta = how much TCS moves relative to the market. Core input to CAPM.
# We compute our OWN rather than copying one — methodology is ours to defend.
import numpy as np

# 5 years of WEEKLY adjusted-close prices (weekly = cleaner signal than daily)
tcs_px   = yf.Ticker("TCS.NS").history(period="5y", interval="1wk")["Close"]
nifty_px = yf.Ticker("^NSEI").history(period="5y", interval="1wk")["Close"]

# align both on the same dates, then turn prices into weekly returns
px   = pd.concat([tcs_px.rename("TCS"), nifty_px.rename("NIFTY")], axis=1).dropna()
rets = px.pct_change().dropna()

# beta = covariance(stock, market) / variance(market)
cov_matrix = np.cov(rets["TCS"], rets["NIFTY"])
beta = cov_matrix[0, 1] / cov_matrix[1, 1]

# cross-check: the slope of an OLS regression line IS beta — same number
slope, intercept = np.polyfit(rets["NIFTY"], rets["TCS"], 1)

print(f"Data points (weeks): {len(rets)}")
print(f"Beta (cov/var):      {beta:.3f}")
print(f"Beta (regression):   {slope:.3f}   <- should match")

# VISUAL — each dot = one week; the red line's slope is beta
plt.figure(figsize=(6, 6))
plt.scatter(rets["NIFTY"]*100, rets["TCS"]*100, alpha=0.5, color="#4C72B0")
plt.plot(rets["NIFTY"]*100, (slope*rets["NIFTY"]+intercept)*100,
         color="#C44E52", linewidth=2, label=f"slope (β) = {slope:.2f}")
plt.axhline(0, color="grey", lw=0.5); plt.axvline(0, color="grey", lw=0.5)
plt.xlabel("Nifty 50 weekly return (%)")
plt.ylabel("TCS weekly return (%)")
plt.title("TCS vs Nifty — beta is the slope")
plt.legend()
plt.tight_layout()
plt.show()

# --- Stage 5b: assemble WACC ---
# WACC = (E/V)*Ke + (D/V)*Kd_aftertax ;  Ke via CAPM = Rf + beta*ERP

# ASSUMPTIONS you choose & defend:
Rf        = 0.0715   # 10-yr GoI G-sec yield (~Oct 2026, near 2-yr high)
ERP       = 0.06     # equity risk premium, Indian large-cap (Damodaran ~7%, this is mild-conservative)
Kd_pretax = 0.075    # TCS ~AAA: borrows near Rf + thin spread (NOT lease-interest/debt)
tax       = 0.24     # latest effective tax rate (FY26)
# beta is already in memory from Stage 5a

# capital weights — E from Stage 1's market_cap; D = total debt
E = market_cap / 1e7      # rupees -> ₹ crore, to match D's units
D = 8000                  # <-- VERIFY: Screener balance sheet "Borrowings"(+leases). Immaterial to result.
V = E + D

Ke   = Rf + beta * ERP            # CAPM cost of equity
Kd   = Kd_pretax * (1 - tax)      # after-tax cost of debt
WACC = (E / V) * Ke + (D / V) * Kd

print(f"Cost of equity (Ke): {Ke:.2%}")
print(f"After-tax Kd:        {Kd:.2%}")
print(f"Equity weight E/V:   {E/V:.2%}")
print(f"Debt weight   D/V:   {D/V:.2%}")
print(f"WACC:                {WACC:.2%}")

# --- Stage 6: discount everything to today & value the company ---
g_terminal = 0.05   # <-- YOUR assumption: perpetual growth after year 5 (must be < WACC and < explicit g)

# 1) PV of the 5 explicit forecast FCFFs: each divided by (1+WACC)^t
fc["t"]  = range(1, forecast_years + 1)            # years 1..5 from today
fc["PV"] = fc["FCFF"] / (1 + WACC) ** fc["t"]

# 2) Terminal value at END of year 5 (Gordon growth), then discounted back to today
fcff_year5 = fc["FCFF"].iloc[-1]
TV         = fcff_year5 * (1 + g_terminal) / (WACC - g_terminal)
PV_TV      = TV / (1 + WACC) ** forecast_years

# 3) Enterprise Value = PV(explicit flows) + PV(terminal value)
EV = fc["PV"].sum() + PV_TV

# 4) Equity Value = EV - Net Debt. TCS holds far MORE cash+investments than debt,
#    so net debt is negative (net CASH) and gets added. We add it separately because
#    we deliberately kept non-operating treasury income OUT of FCFF back in Stage 3.
net_cash   = 55000        # <-- VERIFY: (Cash + Investments) - Total Debt from balance sheet (₹ cr)
equity_val = EV + net_cash

# 5) Intrinsic value per share
shares_cr       = shares_out / 1e7              # -> 361.81 crore shares (from Stage 1)
intrinsic_price = equity_val / shares_cr        # ₹ crore / crore shares = ₹ per share

print(f"Sum PV of explicit FCFF: ₹{fc['PV'].sum():>10,.0f} cr")
print(f"Terminal value (@FY31):  ₹{TV:>10,.0f} cr")
print(f"PV of terminal value:    ₹{PV_TV:>10,.0f} cr   ({PV_TV/EV:.0%} of EV)")
print(f"Enterprise Value:        ₹{EV:>10,.0f} cr")
print(f"Equity Value:            ₹{equity_val:>10,.0f} cr")
print(f"-----")
print(f"Intrinsic value / share: ₹{intrinsic_price:,.0f}")
print(f"Live market price:       ₹{price:,.0f}")
print(f"Verdict: {'UNDERvalued' if intrinsic_price > price else 'OVERvalued'} "
      f"({(intrinsic_price/price - 1):+.0%} vs market)")

# --- Stage 7: sensitivity heatmap — intrinsic value across WACC x terminal growth ---
# We wrap the whole valuation in a function so we can call it hundreds of times
# across a grid. Same logic as Stage 6 — just parameterised.

def intrinsic_value(wacc, g_term):
    pv_explicit = sum(fc["FCFF"].iloc[n-1] / (1 + wacc) ** n
                      for n in range(1, forecast_years + 1))
    tv    = fc["FCFF"].iloc[-1] * (1 + g_term) / (wacc - g_term)
    pv_tv = tv / (1 + wacc) ** forecast_years
    equity = pv_explicit + pv_tv + net_cash
    return equity / shares_cr

# the two axes we flex (base case sits inside each range)
wacc_range = np.arange(0.110, 0.1451, 0.005)   # 11.0% .. 14.5%
g_range    = np.arange(0.030, 0.0601, 0.005)   # 3.0%  .. 6.0%

# matrix of intrinsic values: rows = terminal g, cols = WACC
matrix = np.array([[intrinsic_value(w, g) for w in wacc_range] for g in g_range])

# readable table
heat = pd.DataFrame(matrix,
                    index=[f"g={g:.1%}" for g in g_range],
                    columns=[f"{w:.1%}" for w in wacc_range])
print(heat.round(0).to_string())

# HEATMAP — green = intrinsic ABOVE market (undervalued), red = BELOW (overvalued)
fig, ax = plt.subplots(figsize=(10, 6))
span = np.abs(matrix - price).max()
im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto",
               vmin=price - span, vmax=price + span)   # colour centred on market price

ax.set_xticks(range(len(wacc_range)), [f"{w:.1%}" for w in wacc_range])
ax.set_yticks(range(len(g_range)),    [f"{g:.1%}" for g in g_range])
ax.set_xlabel("WACC"); ax.set_ylabel("Terminal growth (g)")
ax.set_title(f"TCS intrinsic value / share (₹)   —   market price ₹{price:,.0f}")

for i in range(len(g_range)):
    for j in range(len(wacc_range)):
        ax.text(j, i, f"{matrix[i,j]:,.0f}", ha="center", va="center", fontsize=8)

plt.colorbar(im, label="₹ / share")
plt.tight_layout()
plt.show()