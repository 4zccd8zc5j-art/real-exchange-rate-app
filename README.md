# Real Exchange Rate App (FINC-470)

A Streamlit app that computes the bilateral **real exchange rate** between any two
IMF economies (plus the Euro area) from monthly IMF consumer-price and
exchange-rate data starting in January 1976.

**Live app:** _add your Streamlit URL here after deploying_

## What the app does

1. You pick **Country 1** and **Country 2** from 190 economies (189 countries and
   territories plus the Euro area, `G163`) and a **start / end month**.
2. The app downloads four monthly series from the IMF:
   the price index of each country and the exchange rate of each country against
   the US dollar.
3. It computes, for every month `t`:

   | Symbol | Definition |
   |---|---|
   | `S(t)` | units of Country 2 currency per **one** unit of Country 1 currency |
   | `P1(t)`, `P2(t)` | monthly consumer price index of Country 1 and Country 2 |
   | `RER(t)` | `S(t) × P1(t) / P2(t)` |
   | `RER*` | average of `RER(t)` over the **valid** months of the selected sample |
   | `Real Index(t)` | `100 × RER(t) / RER*` |

   `RER*` is recomputed every time the dates change, so the real index always
   averages 100 over the chosen sample.
4. You choose **Real**, **Nominal**, or **Both** in an interactive Plotly chart.
   The nominal series `S(t)` is plotted in actual currency units (never
   normalised). **Both** shows the two series in separate panels with separate
   axes, sharing the time axis.
5. A **Download CSV** button exports every month in the sample with all inputs and
   calculations, and an expander shows the worked calculation for any single month.

## Data source and keys

Everything comes from the IMF SDMX 3.0 REST API, `https://api.imf.org/external/sdmx/3.0`,
requested as SDMX-CSV (`Accept: application/vnd.sdmx.data+csv;version=2.0.0`).
No API key is required.

| Series | Dataflow | Key |
|---|---|---|
| Consumer price index (monthly, all items) | `IMF.STA:CPI` | `{ISO3}.CPI._T.IX.M` |
| Euro area price index (harmonised) | `IMF.STA:CPI` | `G163.HICP._T.IX.M` (used when the CPI key is empty) |
| Exchange rate, period average, local currency per USD | `IMF.STA:ER` | `{ISO3}.XDC_USD.PA_RT.M` |

Because the IMF quotes exchange rates as **local currency units per US dollar**,
the app converts them to the stated direction:

```
S(t) = (Country 2 LCU per USD) / (Country 1 LCU per USD)
```

Example: with the United Kingdom as Country 1 and the United States as Country 2,
the IMF gives GBP per USD for the UK and 1.0 for the US, so
`S(t) = 1 / (GBP per USD) = USD per GBP`.

A month is **valid** when `S(t)`, `P1(t)` and `P2(t)` are all present and positive.
Months with missing inputs stay in the table and the CSV (flagged `valid = False`)
but are excluded from `RER*`.

## CSV columns

| Column | Meaning |
|---|---|
| `month` | `YYYY-MM` |
| `country_1`, `country_2` | ISO3 codes selected |
| `p1_index_type`, `p2_index_type` | `CPI` or `HICP` |
| `fx1_lcu_per_usd`, `fx2_lcu_per_usd` | IMF exchange rates, local currency per USD |
| `S_c2_per_c1` | `S(t)`, Country 2 currency per one unit of Country 1 currency |
| `P1_cpi`, `P2_cpi` | price indices |
| `RER` | `S × P1 / P2` |
| `RER_star` | sample average of `RER` (same value on every row) |
| `real_index` | `100 × RER / RER_star` |
| `valid` | whether the month entered the `RER*` average |

## Running locally

Requires Python 3.12 (3.9 or later works).

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying on Streamlit Community Cloud

1. Push `app.py`, `requirements.txt` and `README.md` to the top level of a public
   GitHub repository.
2. Sign in at <https://share.streamlit.io> with GitHub, choose **Create app**,
   select the repository, branch `main` and main file `app.py`.
3. Under **Advanced settings** choose Python 3.12 and leave Secrets empty.
4. Deploy.

## Checking the economics (UK vs US example)

1. Select **United Kingdom (GBR)** as Country 1 and **United States (USA)** as
   Country 2. The nominal chart is labelled `USD per 1 GBP`, and values around
   1.2 to 1.4 in recent years confirm the direction.
2. Change the start and end months. `RER*` updates and the metric
   "Average real index" stays at 100.00. In the exported CSV, the mean of
   `real_index` over rows with `valid = True` is 100.
3. Open **Verify one month's calculation**: it shows the IMF inputs and the
   arithmetic for `S`, `RER` and the real index for any month, so you can repeat
   the calculation by hand from the CSV.
4. Try **Real**, **Nominal** and **Both**.

## Known data limitations

- **Coverage gaps.** Many economies have price or exchange-rate data starting
  after 1976, or with missing months. The app uses whatever overlap exists and
  reports the coverage of each input under *Data notes*.
- **Euro area.** The IMF publishes the Euro area price index only as an HICP,
  starting in December 1999; its exchange rate starts in January 1999.
- **Euro members.** For countries that adopted the euro (Germany, France, Italy,
  and so on), the IMF national exchange-rate series ends the month before
  adoption, so complete data for them stop there (for example December 1998 for
  Germany). The app says so under *Data notes*; use the Euro area (`G163`) for
  the euro period.
- **Missing months.** Some months are missing even for large economies; for
  example the US CPI for October 2025 was not published. Such months are kept in
  the table and CSV with `valid = False` and excluded from `RER*`.
- **Base years.** Each country's price index has its own base year, so the level
  of `RER(t)` depends on those bases. Only the real **index** (relative to the
  sample average) is comparable; that is why the app normalises it.
- **Live downloads.** The IMF API occasionally times out. Responses are cached
  for 12 hours; if a download fails, the app shows the error and you can retry.

## Files

- `app.py` – the Streamlit application
- `requirements.txt` – Python dependencies
- `README.md` – this file
