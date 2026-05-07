# GPU Price Tracker — Streamlit Dashboard

Public-facing visualization for the cross-cloud GPU pricing data collected
by this repo. Reads `gpu_prices.db` from a private S3 bucket using a
read-only IAM user, caches in memory for an hour, and renders three views:
latest prices, price trends per GPU family, and spot-vs-on-demand spread.

## Local development

```bash
pip install -r streamlit_app/requirements.txt

# Option A: use the checked-in DB (no AWS needed)
LOCAL_DB=1 streamlit run streamlit_app/app.py

# Option B: pull from S3 with real credentials
cp streamlit_app/.streamlit/secrets.toml.example \
   streamlit_app/.streamlit/secrets.toml
# fill in keys, then:
streamlit run streamlit_app/app.py
```

`streamlit_app/.streamlit/secrets.toml` is gitignored — never commit it.

## Deploy to Streamlit Community Cloud

1. **Create a read-only IAM user** (one-time, in AWS console):
   - User name: `gpu-price-streamlit-reader`
   - Inline policy:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::hubbard-gpu-price-data/gpu_prices.db"
       }]
     }
     ```
   - Generate an access key for the user and save the secret.

2. **Create the Streamlit app** at https://share.streamlit.io:
   - Repository: `alex-hubbard/gpu_price_tracker`
   - Branch: `main`
   - Main file path: `streamlit_app/app.py`
   - Python version: 3.11

3. **Paste secrets** into the app's *Settings → Secrets* panel (TOML format):
   ```toml
   [aws]
   access_key_id = "AKIA..."
   secret_access_key = "..."
   bucket = "hubbard-gpu-price-data"
   key = "gpu_prices.db"
   region = "us-east-1"
   ```

4. Deploy. The app downloads the DB on first load and caches it for
   one hour; new snapshots show up at most an hour after the GitHub
   Action uploads them.

## How it works

- `queries.py` handles S3 download and SQL query helpers, all wrapped in
  `@st.cache_data` / `@st.cache_resource` with a 1-hour TTL.
- `app.py` is a single page with a KPI header, sidebar filters
  (GPU, provider, spot/on-demand, lookback), and three tabs.
- Database schema is documented in `../database.py` and
  `../MODELING_GPU_USAGE_TRENDS.md`.
