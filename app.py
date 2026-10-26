"""
Real Exchange Rate Explorer  (FINC-470)

A Streamlit app that downloads monthly consumer-price and exchange-rate data from
the IMF and computes the bilateral real exchange rate between any two economies.

Data source: IMF SDMX 3.0 REST API  (https://api.imf.org/external/sdmx/3.0)
  * Consumer prices  - dataflow IMF.STA:CPI, key  {ISO3}.CPI._T.IX.M
                       The Euro area (G163) is only published as a harmonised
                       index, so the app falls back to {ISO3}.HICP._T.IX.M when
                       the plain CPI key returns nothing.
  * Exchange rates   - dataflow IMF.STA:ER,  key  {ISO3}.XDC_USD.PA_RT.M
                       (domestic-currency units per US dollar, period average)

Definitions used throughout the app
  S(t)          units of Country 2 currency per ONE unit of Country 1 currency
                = (LCU2 per USD) / (LCU1 per USD)
  P1(t), P2(t)  monthly consumer price indices of Country 1 and Country 2
  RER(t)        = S(t) * P1(t) / P2(t)
  RER*          = average of RER(t) over the valid months of the selected sample
  Real Index(t) = 100 * RER(t) / RER*

Compatible with Python 3.12 (also runs on 3.9+).
"""
from __future__ import annotations

import io
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMF_API = "https://api.imf.org/external/sdmx/3.0"
CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=2.0.0"
REQUEST_TIMEOUT = 90           # seconds per IMF request
CACHE_TTL = 12 * 60 * 60       # seconds; IMF series update monthly
FIRST_PERIOD = pd.Period("1976-01", freq="M")

COLOR_REAL = "#2a78d6"         # blue  - real exchange rate index
COLOR_NOMINAL = "#eb6834"      # orange - nominal exchange rate
COLOR_REFERENCE = "#898781"    # muted gray - the RER* = 100 reference line

# Economies with both a monthly price index and a monthly exchange rate in the
# IMF database (189 countries/territories plus the Euro area aggregate G163).
# Names follow the IMF country codelist.
COUNTRIES = {
    "AFG": "Afghanistan, Islamic Republic of",
    "ALB": "Albania",
    "DZA": "Algeria",
    "AGO": "Angola",
    "ATG": "Antigua and Barbuda",
    "ARG": "Argentina",
    "ARM": "Armenia, Republic of",
    "ABW": "Aruba, Kingdom of the Netherlands",
    "AUS": "Australia",
    "AUT": "Austria",
    "AZE": "Azerbaijan, Republic of",
    "BHS": "Bahamas, The",
    "BHR": "Bahrain, Kingdom of",
    "BGD": "Bangladesh",
    "BRB": "Barbados",
    "BLR": "Belarus, Republic of",
    "BEL": "Belgium",
    "BLZ": "Belize",
    "BEN": "Benin",
    "BTN": "Bhutan",
    "BOL": "Bolivia",
    "BIH": "Bosnia and Herzegovina",
    "BWA": "Botswana",
    "BRA": "Brazil",
    "BRN": "Brunei Darussalam",
    "BGR": "Bulgaria",
    "BFA": "Burkina Faso",
    "BDI": "Burundi",
    "CPV": "Cabo Verde",
    "KHM": "Cambodia",
    "CMR": "Cameroon",
    "CAN": "Canada",
    "CAF": "Central African Republic",
    "TCD": "Chad",
    "CHL": "Chile",
    "CHN": "China, People's Republic of",
    "COL": "Colombia",
    "COM": "Comoros, Union of the",
    "COD": "Congo, Democratic Republic of the",
    "COG": "Congo, Republic of",
    "CRI": "Costa Rica",
    "HRV": "Croatia, Republic of",
    "CUW": "Curaçao, Kingdom of the Netherlands",
    "CYP": "Cyprus",
    "CZE": "Czech Republic",
    "CIV": "Côte d'Ivoire",
    "DNK": "Denmark",
    "DJI": "Djibouti",
    "DMA": "Dominica",
    "DOM": "Dominican Republic",
    "ECU": "Ecuador",
    "EGY": "Egypt, Arab Republic of",
    "SLV": "El Salvador",
    "GNQ": "Equatorial Guinea, Republic of",
    "EST": "Estonia, Republic of",
    "SWZ": "Eswatini, Kingdom of",
    "ETH": "Ethiopia, The Federal Democratic Republic of",
    "G163": "Euro Area (EA)",
    "FJI": "Fiji, Republic of",
    "FIN": "Finland",
    "FRA": "France",
    "GAB": "Gabon",
    "GMB": "Gambia, The",
    "GEO": "Georgia",
    "DEU": "Germany",
    "GHA": "Ghana",
    "GRC": "Greece",
    "GRD": "Grenada",
    "GLP": "Guadeloupe",
    "GTM": "Guatemala",
    "GIN": "Guinea",
    "GNB": "Guinea-Bissau",
    "GUY": "Guyana",
    "HTI": "Haiti",
    "HND": "Honduras",
    "HKG": "Hong Kong Special Administrative Region, People's Republic of China",
    "HUN": "Hungary",
    "ISL": "Iceland",
    "IND": "India",
    "IDN": "Indonesia",
    "IRN": "Iran, Islamic Republic of",
    "IRQ": "Iraq",
    "IRL": "Ireland",
    "ISR": "Israel",
    "ITA": "Italy",
    "JAM": "Jamaica",
    "JPN": "Japan",
    "JOR": "Jordan",
    "KAZ": "Kazakhstan, Republic of",
    "KEN": "Kenya",
    "KIR": "Kiribati",
    "KOR": "Korea, Republic of",
    "KOS": "Kosovo, Republic of",
    "KWT": "Kuwait",
    "KGZ": "Kyrgyz Republic",
    "LAO": "Lao People's Democratic Republic",
    "LVA": "Latvia, Republic of",
    "LBN": "Lebanon",
    "LSO": "Lesotho, Kingdom of",
    "LBR": "Liberia",
    "LBY": "Libya",
    "LTU": "Lithuania, Republic of",
    "LUX": "Luxembourg",
    "MAC": "Macao Special Administrative Region, People's Republic of China",
    "MDG": "Madagascar, Republic of",
    "MWI": "Malawi",
    "MYS": "Malaysia",
    "MDV": "Maldives",
    "MLI": "Mali",
    "MLT": "Malta",
    "MTQ": "Martinique",
    "MRT": "Mauritania, Islamic Republic of",
    "MUS": "Mauritius",
    "MEX": "Mexico",
    "MDA": "Moldova, Republic of",
    "MNG": "Mongolia",
    "MNE": "Montenegro",
    "MSR": "Montserrat, United Kingdom-British Overseas Territory",
    "MAR": "Morocco",
    "MOZ": "Mozambique, Republic of",
    "MMR": "Myanmar",
    "NAM": "Namibia",
    "NRU": "Naoero, Republic of",
    "NPL": "Nepal",
    "NLD": "Netherlands, The",
    "NCL": "New Caledonia",
    "NIC": "Nicaragua",
    "NER": "Niger",
    "NGA": "Nigeria",
    "MKD": "North Macedonia, Republic of",
    "NOR": "Norway",
    "OMN": "Oman",
    "PAK": "Pakistan",
    "PAN": "Panama",
    "PRY": "Paraguay",
    "PER": "Peru",
    "PHL": "Philippines",
    "POL": "Poland, Republic of",
    "PRT": "Portugal",
    "QAT": "Qatar",
    "ROU": "Romania",
    "RUS": "Russian Federation",
    "RWA": "Rwanda",
    "WSM": "Samoa",
    "SMR": "San Marino, Republic of",
    "SAU": "Saudi Arabia",
    "SEN": "Senegal",
    "SRB": "Serbia, Republic of",
    "SYC": "Seychelles",
    "SLE": "Sierra Leone",
    "SGP": "Singapore",
    "SXM": "Sint Maarten, Kingdom of the Netherlands",
    "SVK": "Slovak Republic",
    "SVN": "Slovenia, Republic of",
    "SLB": "Solomon Islands",
    "SOM": "Somalia",
    "ZAF": "South Africa",
    "SSD": "South Sudan, Republic of",
    "ESP": "Spain",
    "LKA": "Sri Lanka",
    "KNA": "St. Kitts and Nevis",
    "LCA": "St. Lucia",
    "VCT": "St. Vincent and the Grenadines",
    "SDN": "Sudan",
    "SUR": "Suriname",
    "SWE": "Sweden",
    "CHE": "Switzerland",
    "SYR": "Syrian Arab Republic",
    "STP": "São Tomé and Príncipe, Democratic Republic of",
    "TJK": "Tajikistan, Republic of",
    "TZA": "Tanzania, United Republic of",
    "THA": "Thailand",
    "TLS": "Timor-Leste, Democratic Republic of",
    "TGO": "Togo",
    "TON": "Tonga",
    "TTO": "Trinidad and Tobago",
    "TUN": "Tunisia",
    "TUR": "Türkiye, Republic of",
    "UGA": "Uganda",
    "UKR": "Ukraine",
    "ARE": "United Arab Emirates",
    "GBR": "United Kingdom",
    "USA": "United States",
    "URY": "Uruguay",
    "UZB": "Uzbekistan, Republic of",
    "VEN": "Venezuela, República Bolivariana de",
    "VNM": "Vietnam",
    "YEM": "Yemen, Republic of",
    "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}

# Current ISO 4217 currency codes, used only to label the nominal exchange rate.
# Economies not listed here are labelled with their country name instead.
CURRENCY = {
    "G163": "EUR", "USA": "USD", "GBR": "GBP", "JPN": "JPY", "CHN": "CNY", "CAN": "CAD",
    "AUS": "AUD", "CHE": "CHF", "SWE": "SEK", "NOR": "NOK", "DNK": "DKK", "ISL": "ISK",
    "KOR": "KRW", "IND": "INR", "BRA": "BRL", "MEX": "MXN", "RUS": "RUB", "ZAF": "ZAR",
    "TUR": "TRY", "SGP": "SGD", "HKG": "HKD", "MAC": "MOP", "IDN": "IDR", "MYS": "MYR",
    "THA": "THB", "PHL": "PHP", "VNM": "VND", "KHM": "KHR", "LAO": "LAK", "MMR": "MMK",
    "MNG": "MNT", "BRN": "BND", "ISR": "ILS", "SAU": "SAR", "ARE": "AED", "QAT": "QAR",
    "KWT": "KWD", "BHR": "BHD", "OMN": "OMR", "JOR": "JOD", "LBN": "LBP", "IRQ": "IQD",
    "IRN": "IRR", "EGY": "EGP", "MAR": "MAD", "TUN": "TND", "DZA": "DZD", "LBY": "LYD",
    "NGA": "NGN", "GHA": "GHS", "KEN": "KES", "TZA": "TZS", "UGA": "UGX", "RWA": "RWF",
    "ETH": "ETB", "ZMB": "ZMW", "MOZ": "MZN", "AGO": "AOA", "BWA": "BWP", "NAM": "NAD",
    "MUS": "MUR", "SYC": "SCR", "MDG": "MGA", "MWI": "MWK", "LSO": "LSL", "SWZ": "SZL",
    "ARG": "ARS", "CHL": "CLP", "COL": "COP", "PER": "PEN", "URY": "UYU", "PRY": "PYG",
    "BOL": "BOB", "VEN": "VES", "GUY": "GYD", "SUR": "SRD", "CRI": "CRC", "GTM": "GTQ",
    "HND": "HNL", "NIC": "NIO", "DOM": "DOP", "JAM": "JMD", "TTO": "TTD", "BRB": "BBD",
    "BHS": "BSD", "BLZ": "BZD", "HTI": "HTG", "CZE": "CZK", "HUN": "HUF", "POL": "PLN",
    "ROU": "RON", "BGR": "BGN", "UKR": "UAH", "KAZ": "KZT", "UZB": "UZS", "KGZ": "KGS",
    "TJK": "TJS", "GEO": "GEL", "ARM": "AMD", "AZE": "AZN", "BLR": "BYN", "MDA": "MDL",
    "SRB": "RSD", "MKD": "MKD", "ALB": "ALL", "BIH": "BAM", "PAK": "PKR", "BGD": "BDT",
    "LKA": "LKR", "NPL": "NPR", "BTN": "BTN", "MDV": "MVR", "AFG": "AFN", "FJI": "FJD",
    "WSM": "WST", "TON": "TOP", "SLB": "SBD", "PAN": "PAB", "ECU": "USD", "SLV": "USD",
    # Euro area members (observations before euro adoption are in the legacy currency)
    "AUT": "EUR", "BEL": "EUR", "CYP": "EUR", "DEU": "EUR", "ESP": "EUR", "EST": "EUR",
    "FIN": "EUR", "FRA": "EUR", "GRC": "EUR", "HRV": "EUR", "IRL": "EUR", "ITA": "EUR",
    "LTU": "EUR", "LUX": "EUR", "LVA": "EUR", "MLT": "EUR", "NLD": "EUR", "PRT": "EUR",
    "SVK": "EUR", "SVN": "EUR", "SMR": "EUR", "MNE": "EUR", "KOS": "EUR", "GLP": "EUR",
    "MTQ": "EUR",
    # Currency unions
    "BEN": "XOF", "BFA": "XOF", "CIV": "XOF", "GNB": "XOF", "MLI": "XOF", "NER": "XOF",
    "SEN": "XOF", "TGO": "XOF",
    "CMR": "XAF", "CAF": "XAF", "TCD": "XAF", "COG": "XAF", "GNQ": "XAF", "GAB": "XAF",
    "ATG": "XCD", "DMA": "XCD", "GRD": "XCD", "KNA": "XCD", "LCA": "XCD", "VCT": "XCD",
    "MSR": "XCD",
}

# Month in which each member adopted the euro. The IMF's national exchange-rate
# series ends the month before adoption, so complete data for these countries
# stop there; the Euro Area (G163) covers the euro period.
EURO_ADOPTION = {
    "AUT": "1999-01", "BEL": "1999-01", "DEU": "1999-01", "ESP": "1999-01", "FIN": "1999-01",
    "FRA": "1999-01", "IRL": "1999-01", "ITA": "1999-01", "LUX": "1999-01", "NLD": "1999-01",
    "PRT": "1999-01", "GRC": "2001-01", "SVN": "2007-01", "CYP": "2008-01", "MLT": "2008-01",
    "SVK": "2009-01", "EST": "2011-01", "LVA": "2014-01", "LTU": "2015-01", "HRV": "2023-01",
}


class IMFDataError(Exception):
    """Raised when the IMF API cannot be reached or returns an error."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def empty_series() -> pd.Series:
    return pd.Series(dtype=float, index=pd.PeriodIndex([], freq="M"))


def short_name(iso3: str) -> str:
    """'Korea, Republic of' -> 'Korea'."""
    return COUNTRIES.get(iso3, iso3).split(",")[0].strip()


def currency_label(iso3: str) -> str:
    return CURRENCY.get(iso3, f"{short_name(iso3)} currency")


def country_option(iso3: str) -> str:
    return f"{COUNTRIES[iso3]} ({iso3})"


# ---------------------------------------------------------------------------
# IMF data access
# ---------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_imf_series(dataflow: str, key: str) -> pd.Series:
    """Download one monthly IMF series and return it indexed by month (Period).

    Returns an empty Series when the key exists but carries no observations.
    Raises IMFDataError on network or HTTP problems.
    """
    url = f"{IMF_API}/data/dataflow/IMF.STA/{dataflow}/+/{key}"
    try:
        response = requests.get(
            url,
            params={"dimensionAtObservation": "TIME_PERIOD"},
            headers={"Accept": CSV_ACCEPT},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise IMFDataError(f"Could not reach the IMF API for {key}: {exc}") from exc

    if response.status_code == 404:
        return empty_series()
    if response.status_code != 200:
        raise IMFDataError(
            f"The IMF API returned HTTP {response.status_code} for {url}. "
            "The service may be temporarily unavailable; please try again later."
        )

    text = response.text.strip()
    if not text:
        return empty_series()

    raw = pd.read_csv(io.StringIO(text), dtype=str)
    if "TIME_PERIOD" not in raw.columns or "OBS_VALUE" not in raw.columns:
        return empty_series()
    if "FREQUENCY" in raw.columns:
        raw = raw[raw["FREQUENCY"] == "M"]
    raw = raw.dropna(subset=["TIME_PERIOD", "OBS_VALUE"])
    if raw.empty:
        return empty_series()

    # IMF writes monthly periods as "1976-M01"; pandas wants "1976-01".
    periods = pd.PeriodIndex(
        raw["TIME_PERIOD"].str.replace("-M", "-", regex=False), freq="M"
    )
    values = pd.to_numeric(raw["OBS_VALUE"], errors="coerce").to_numpy()
    series = pd.Series(values, index=periods, name=key).dropna()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series[series.index >= FIRST_PERIOD]


def fetch_price_index(iso3: str) -> Tuple[pd.Series, Optional[str]]:
    """Monthly consumer price index. Tries CPI first, then HICP (Euro area)."""
    for index_type in ("CPI", "HICP"):
        series = fetch_imf_series("CPI", f"{iso3}.{index_type}._T.IX.M")
        if not series.empty:
            return series, index_type
    return empty_series(), None


def fetch_lcu_per_usd(iso3: str) -> pd.Series:
    """Monthly period-average exchange rate, domestic currency units per USD."""
    series = fetch_imf_series("ER", f"{iso3}.XDC_USD.PA_RT.M")
    if series.empty and iso3 == "USA":
        # The IMF does publish USA = 1.0, but be safe if that series ever disappears.
        last = pd.Timestamp.today().to_period("M")
        series = pd.Series(1.0, index=pd.period_range(FIRST_PERIOD, last, freq="M"))
    return series


def build_dataset(c1: str, c2: str) -> Tuple[pd.DataFrame, dict]:
    """Assemble inputs and compute S(t) and RER(t) for every month from 1976-01."""
    p1, p1_type = fetch_price_index(c1)
    p2, p2_type = fetch_price_index(c2)
    e1 = fetch_lcu_per_usd(c1)
    e2 = fetch_lcu_per_usd(c2)

    df = pd.concat(
        {"fx1_lcu_per_usd": e1, "fx2_lcu_per_usd": e2, "P1_cpi": p1, "P2_cpi": p2},
        axis=1,
    ).sort_index()

    # IMF rates are LCU per USD. S(t) = Country-2 currency per ONE unit of
    # Country-1 currency = (LCU2/USD) / (LCU1/USD).
    with np.errstate(divide="ignore", invalid="ignore"):
        df["S_c2_per_c1"] = df["fx2_lcu_per_usd"] / df["fx1_lcu_per_usd"]
        df["RER"] = df["S_c2_per_c1"] * df["P1_cpi"] / df["P2_cpi"]

    inputs = df[["S_c2_per_c1", "P1_cpi", "P2_cpi"]].replace([np.inf, -np.inf], np.nan)
    df["valid"] = inputs.notna().all(axis=1) & (inputs > 0).all(axis=1)
    df.loc[~df["valid"], "RER"] = np.nan
    df["S_c2_per_c1"] = df["S_c2_per_c1"].replace([np.inf, -np.inf], np.nan)

    meta = {
        "p1_type": p1_type,
        "p2_type": p2_type,
        "p1_range": (p1.index.min(), p1.index.max()) if not p1.empty else None,
        "p2_range": (p2.index.min(), p2.index.max()) if not p2.empty else None,
        "e1_range": (e1.index.min(), e1.index.max()) if not e1.empty else None,
        "e2_range": (e2.index.min(), e2.index.max()) if not e2.empty else None,
    }
    return df, meta


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def real_trace(sample: pd.DataFrame) -> go.Scatter:
    return go.Scatter(
        x=sample.index.to_timestamp(),
        y=sample["real_index"],
        mode="lines",
        name="Real index",
        line=dict(color=COLOR_REAL, width=2),
        connectgaps=False,
        hovertemplate="Real index: %{y:.2f}<extra></extra>",
    )


def nominal_trace(sample: pd.DataFrame, s_label: str) -> go.Scatter:
    return go.Scatter(
        x=sample.index.to_timestamp(),
        y=sample["S_c2_per_c1"],
        mode="lines",
        name=f"S(t), {s_label}",
        line=dict(color=COLOR_NOMINAL, width=2),
        connectgaps=False,
        hovertemplate="S(t): %{y:.4f}<extra></extra>",
    )


def make_chart(sample: pd.DataFrame, view: str, c1: str, c2: str) -> go.Figure:
    s_label = f"{currency_label(c2)} per 1 {currency_label(c1)}"
    real_title = "Real exchange rate index (sample average = 100)"
    nominal_title = f"Nominal exchange rate S(t): {s_label}"

    if view == "Both":
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
            subplot_titles=(real_title, nominal_title),
        )
        fig.add_trace(real_trace(sample), row=1, col=1)
        fig.add_hline(
            y=100, line_dash="dash", line_color=COLOR_REFERENCE, line_width=1,
            annotation_text="RER* = 100", annotation_position="top left",
            row=1, col=1,
        )
        fig.add_trace(nominal_trace(sample, s_label), row=2, col=1)
        fig.update_yaxes(title_text="Index (RER* = 100)", row=1, col=1)
        fig.update_yaxes(title_text=s_label, row=2, col=1)
        fig.update_xaxes(title_text="Month", row=2, col=1)
        fig.update_layout(height=680)
    elif view == "Real":
        fig = go.Figure(real_trace(sample))
        fig.add_hline(
            y=100, line_dash="dash", line_color=COLOR_REFERENCE, line_width=1,
            annotation_text="RER* = 100", annotation_position="top left",
        )
        fig.update_layout(title=real_title, yaxis_title="Index (RER* = 100)",
                          xaxis_title="Month", height=480)
    else:  # Nominal
        fig = go.Figure(nominal_trace(sample, s_label))
        fig.update_layout(title=nominal_title, yaxis_title=s_label,
                          xaxis_title="Month", height=480)

    fig.update_layout(
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=60, r=30, t=70, b=50),
    )
    fig.update_xaxes(showgrid=False)
    return fig


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Real Exchange Rate Explorer", page_icon="💱",
                       layout="wide")
    st.title("Real Exchange Rate Explorer")
    st.caption(
        "Monthly IMF consumer-price and exchange-rate data from January 1976 "
        "(where available). Choose two economies and a sample period; the app "
        "computes S(t), RER(t), RER* and a real exchange rate index."
    )

    codes = list(COUNTRIES)
    with st.sidebar:
        st.header("Countries")
        c1 = st.selectbox("Country 1", codes, index=codes.index("GBR"),
                          format_func=country_option,
                          help="Its currency is the ONE unit being priced.")
        c2 = st.selectbox("Country 2", codes, index=codes.index("USA"),
                          format_func=country_option,
                          help="S(t) is quoted in units of this country's currency.")
        st.markdown(
            f"**S(t)** = {currency_label(c2)} per 1 {currency_label(c1)}  \n"
            "**RER(t)** = S(t) × P1(t) / P2(t)"
        )

    if c1 == c2:
        st.info("Country 1 and Country 2 are the same, so S(t) = 1 and the real index "
                "is flat at 100. Pick two different economies.")

    with st.spinner("Downloading IMF data..."):
        try:
            df, meta = build_dataset(c1, c2)
        except IMFDataError as exc:
            st.error(str(exc))
            st.stop()

    valid_months = df.index[df["valid"]]
    if len(valid_months) == 0:
        st.error(
            "No overlapping months with a price index and an exchange rate were found "
            f"for {short_name(c1)} and {short_name(c2)} since January 1976."
        )
        with st.expander("Data coverage"):
            st.write(meta)
        st.stop()

    span = pd.period_range(valid_months.min(), valid_months.max(), freq="M")
    span_labels = [str(p) for p in span]

    with st.sidebar:
        st.header("Sample period")
        start_label = st.selectbox("Start month", span_labels, index=0,
                                   key=f"start_{c1}_{c2}")
        end_label = st.selectbox("End month", span_labels, index=len(span_labels) - 1,
                                 key=f"end_{c1}_{c2}")
        st.header("Chart")
        view = st.radio("Series to plot", ["Real", "Nominal", "Both"], index=2,
                        horizontal=True)

    start, end = pd.Period(start_label, freq="M"), pd.Period(end_label, freq="M")
    if start > end:
        start, end = end, start
        st.warning(f"Start was after end; using {start} to {end}.")

    # --- Sample-period calculations (RER* is recomputed whenever dates change) ---
    sample = df.loc[start:end].copy()
    in_sample_valid = sample["RER"].notna()
    n_valid, n_total = int(in_sample_valid.sum()), len(sample)
    if n_valid == 0:
        st.error("The selected period has no month with complete data. Widen the range.")
        st.stop()
    rer_star = float(sample.loc[in_sample_valid, "RER"].mean())
    sample["RER_star"] = rer_star
    sample["real_index"] = 100.0 * sample["RER"] / rer_star

    s_label = f"{currency_label(c2)} per 1 {currency_label(c1)}"
    last_valid = sample.index[in_sample_valid][-1]

    st.subheader(f"{short_name(c1)} vs {short_name(c2)}, {start} to {end}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("RER* (sample average of RER)", f"{rer_star:,.4f}")
    m2.metric("Valid months", f"{n_valid} / {n_total}",
              help="Months with S, P1 and P2 all available, out of months in the sample")
    m3.metric("Average real index", f"{sample['real_index'].mean():.2f}",
              help="Always 100 by construction: the index is RER divided by its sample average")
    m4.metric(f"S in {last_valid}", f"{sample.loc[last_valid, 'S_c2_per_c1']:.4f}",
              help=s_label)

    st.plotly_chart(make_chart(sample, view, c1, c2))

    # --- Notes on the data actually used ---
    notes = []
    for label, code, ptype, prange, erange in (
        ("Country 1", c1, meta["p1_type"], meta["p1_range"], meta["e1_range"]),
        ("Country 2", c2, meta["p2_type"], meta["p2_range"], meta["e2_range"]),
    ):
        p_text = (f"{ptype} {prange[0]} to {prange[1]}" if prange else "not available")
        e_text = (f"{erange[0]} to {erange[1]}" if erange else "not available")
        notes.append(f"- **{label}, {COUNTRIES[code]} ({code})**: price index {p_text}; "
                     f"exchange rate (LCU per USD) {e_text}.")
    if n_valid < n_total:
        notes.append(f"- {n_total - n_valid} month(s) in the sample lack a complete set of "
                     "inputs; they appear in the table and CSV but are excluded from RER*.")
    for code in (c1, c2):
        adoption = EURO_ADOPTION.get(code)
        if adoption:
            last_national = pd.Period(adoption, freq="M") - 1
            notes.append(
                f"- **{short_name(code)}** adopted the euro in {adoption}. The IMF stops "
                "publishing a national exchange rate at that point, so complete data for "
                f"{short_name(code)} end in {last_national}. For the euro period select the "
                "Euro Area (G163) instead."
            )
    st.markdown("**Data notes**\n" + "\n".join(notes))

    # --- Worked verification for one month ---
    with st.expander("Verify one month's calculation"):
        verify_label = st.selectbox(
            "Month to verify", [str(p) for p in sample.index[in_sample_valid]],
            index=n_valid - 1,
        )
        row = sample.loc[pd.Period(verify_label, freq="M")]
        st.markdown(
            f"IMF inputs for {verify_label}:  \n"
            f"- {short_name(c1)} exchange rate = {row['fx1_lcu_per_usd']:.6f} "
            f"{currency_label(c1)} per USD  \n"
            f"- {short_name(c2)} exchange rate = {row['fx2_lcu_per_usd']:.6f} "
            f"{currency_label(c2)} per USD  \n"
            f"- P1 ({short_name(c1)} {meta['p1_type']}) = {row['P1_cpi']:.4f}  \n"
            f"- P2 ({short_name(c2)} {meta['p2_type']}) = {row['P2_cpi']:.4f}\n\n"
            f"S(t) = {row['fx2_lcu_per_usd']:.6f} / {row['fx1_lcu_per_usd']:.6f} = "
            f"**{row['S_c2_per_c1']:.6f}** {s_label}  \n"
            f"RER(t) = S × P1 / P2 = {row['S_c2_per_c1']:.6f} × {row['P1_cpi']:.4f} / "
            f"{row['P2_cpi']:.4f} = **{row['RER']:.6f}**  \n"
            f"Real index = 100 × RER / RER* = 100 × {row['RER']:.6f} / {rer_star:.6f} = "
            f"**{row['real_index']:.4f}**"
        )

    # --- Table and CSV download ---
    export = sample.rename_axis("month").reset_index()
    export["month"] = export["month"].astype(str)
    export.insert(1, "country_1", c1)
    export.insert(2, "country_2", c2)
    export.insert(3, "p1_index_type", meta["p1_type"])
    export.insert(4, "p2_index_type", meta["p2_type"])
    export = export[[
        "month", "country_1", "country_2", "p1_index_type", "p2_index_type",
        "fx1_lcu_per_usd", "fx2_lcu_per_usd", "S_c2_per_c1", "P1_cpi", "P2_cpi",
        "RER", "RER_star", "real_index", "valid",
    ]]

    st.download_button(
        label="Download CSV (all observations and calculations in the sample)",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name=f"rer_{c1}_{c2}_{start}_{end}.csv",
        mime="text/csv",
    )
    with st.expander("Show data table"):
        st.dataframe(
            export,
            hide_index=True,
            column_config={
                "fx1_lcu_per_usd": st.column_config.NumberColumn(format="%.6f"),
                "fx2_lcu_per_usd": st.column_config.NumberColumn(format="%.6f"),
                "S_c2_per_c1": st.column_config.NumberColumn(format="%.6f"),
                "P1_cpi": st.column_config.NumberColumn(format="%.4f"),
                "P2_cpi": st.column_config.NumberColumn(format="%.4f"),
                "RER": st.column_config.NumberColumn(format="%.6f"),
                "RER_star": st.column_config.NumberColumn(format="%.6f"),
                "real_index": st.column_config.NumberColumn(format="%.4f"),
            },
        )

    st.caption(
        "Source: IMF Data (api.imf.org, SDMX 3.0): dataflow IMF.STA:CPI "
        "(keys {ISO3}.CPI._T.IX.M, or {ISO3}.HICP._T.IX.M for the Euro area) and "
        "dataflow IMF.STA:ER (key {ISO3}.XDC_USD.PA_RT.M, period-average LCU per USD). "
        "Price-index levels use each country's own base year, so RER* and the real "
        "index are meaningful but the level of RER(t) is not comparable across pairs."
    )


if __name__ == "__main__":
    main()
