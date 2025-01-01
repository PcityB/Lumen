#!/usr/bin/env python3
import os
import sys
import logging
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.preprocessing import MinMaxScaler
import joblib
import boto3

##############################################################################
# 1) AWS S3 HELPER FUNCTIONS
##############################################################################
def get_s3_client():
    """
    Builds a boto3 S3 client with region/key/secret from environment variables.
    """
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "us-east-2"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )

def download_file_from_s3(s3_key: str, local_path: str):
    """
    Always re-download a file from s3://<bucket>/<s3_key>, overwriting local_path if it exists.
    """
    bucket_name = os.getenv("LUMEN_S3_BUCKET_NAME", "your-default-bucket")
    s3 = get_s3_client()
    if os.path.exists(local_path):
        logging.info(f"[download_file_from_s3] Removing existing local file => {local_path}")
        os.remove(local_path)

    logging.info(f"[download_file_from_s3] Downloading s3://{bucket_name}/{s3_key} → {local_path}")
    s3.download_file(bucket_name, s3_key, local_path)
    logging.info("[download_file_from_s3] Done.")

def upload_file_to_s3(local_path: str, s3_key: str):
    """
    Uploads a local file to the given s3://<bucket>/<s3_key>.
    """
    bucket_name = os.getenv("LUMEN_S3_BUCKET_NAME", "your-default-bucket")
    s3 = get_s3_client()
    try:
        logging.info(f"[upload_file_to_s3] Uploading {local_path} → s3://{bucket_name}/{s3_key}")
        s3.upload_file(local_path, bucket_name, s3_key)
        logging.info("[upload_file_to_s3] Done.")
    except Exception as e:
        logging.error(f"Error uploading {local_path} to S3: {e}")
        raise

def auto_upload_file_to_s3(local_path: str, s3_subfolder: str = ""):
    """
    Convenience wrapper that derives the filename from local_path
    and optionally places it in s3_subfolder.
    """
    base_name = os.path.basename(local_path)
    if s3_subfolder:
        s3_key = f"{s3_subfolder}/{base_name}"
    else:
        s3_key = base_name
    upload_file_to_s3(local_path, s3_key)

##############################################################################
# 2) ENV, LOGGING, AND PATH SETUP
##############################################################################
load_dotenv()
logging.basicConfig(level=logging.INFO)

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
sys.path.append(project_root)

BASE_DIR     = os.path.abspath(os.path.join(script_dir, "..", ".."))
DATA_DIR     = os.path.join(BASE_DIR, "data", "lumen_2", "processed")
FEATURED_DIR = os.path.join(BASE_DIR, "data", "lumen_2", "featured")
SEQUENCES_DIR= os.path.join(FEATURED_DIR, "sequences")
MODEL_DIR    = os.path.join(BASE_DIR, "models", "lumen_2")  # <-- Define MODEL_DIR
SCALER_DIR   = os.path.join(MODEL_DIR, "scalers")           # <-- And SCALER_DIR

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FEATURED_DIR, exist_ok=True)
os.makedirs(SEQUENCES_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(SCALER_DIR, exist_ok=True)

##############################################################################
# 3) DOWNLOAD PROCESSED CSVs
##############################################################################
def download_processed_csvs():
    """
    Retrieves processed CSVs for real_time_spx, real_time_spy, real_time_vix from S3
    and overwrites local versions if they exist (due to updated data).
    """
    spx_s3_key = "data/lumen2/processed/processed_real_time_spx.csv"
    spy_s3_key = "data/lumen2/processed/processed_real_time_spy.csv"
    vix_s3_key = "data/lumen2/processed/processed_real_time_vix.csv"

    spx_local = os.path.join(DATA_DIR, "processed_real_time_spx.csv")
    spy_local = os.path.join(DATA_DIR, "processed_real_time_spy.csv")
    vix_local = os.path.join(DATA_DIR, "processed_real_time_vix.csv")

    download_file_from_s3(spx_s3_key, spx_local)
    download_file_from_s3(spy_s3_key, spy_local)
    download_file_from_s3(vix_s3_key, vix_local)

##############################################################################
# 4) MERGE SPX, SPY, VIX
##############################################################################
def merge_spx_spy_vix_3min():
    """
    Loads local CSVs, renames columns, up-samples VIX to 3-min intervals,
    merges everything into one DataFrame, and forward-fills missing data.
    """
    spx_local = os.path.join(DATA_DIR, "processed_real_time_spx.csv")
    spy_local = os.path.join(DATA_DIR, "processed_real_time_spy.csv")
    vix_local = os.path.join(DATA_DIR, "processed_real_time_vix.csv")

    logging.info(f"[merge_spx_spy_vix_3min] Reading {spx_local}, {spy_local}, {vix_local}")
    spx = pd.read_csv(spx_local)
    spy = pd.read_csv(spy_local)
    vix = pd.read_csv(vix_local)

    # Convert timestamps
    spx["timestamp"] = pd.to_datetime(spx["timestamp"], errors="coerce")
    spy["timestamp"] = pd.to_datetime(spy["timestamp"], errors="coerce")
    vix["timestamp"] = pd.to_datetime(vix["timestamp"], errors="coerce")

    # Sort
    spx.sort_values("timestamp", inplace=True)
    spy.sort_values("timestamp", inplace=True)
    vix.sort_values("timestamp", inplace=True)

    # Set index
    spx.set_index("timestamp", inplace=True)
    spy.set_index("timestamp", inplace=True)
    vix.set_index("timestamp", inplace=True)

    # Rename columns for clarity
    if "current_price" in spx.columns:
        spx.rename(columns={"current_price": "spx_price"}, inplace=True)
    if "volume" in spx.columns:
        spx.rename(columns={"volume": "spx_volume"}, inplace=True)
    if "current_price" in spy.columns:
        spy.rename(columns={"current_price": "spy_price"}, inplace=True)
    if "volume" in spy.columns:
        spy.rename(columns={"volume": "spy_volume"}, inplace=True)

    # Resample VIX to 3-min
    vix_3min = vix.resample("3Min").last().ffill()
    if "current_price" in vix_3min.columns:
        vix_3min.rename(columns={"current_price": "vix_price"}, inplace=True)
    if "volume" in vix_3min.columns:
        vix_3min.rename(columns={"volume": "vix_volume"}, inplace=True)

    # Merge SPX + SPY
    merged_spx_spy = spx.join(spy, how="outer", lsuffix="_spx", rsuffix="_spy")
    # Then join with vix_3min
    df_merged = merged_spx_spy.join(vix_3min, how="outer", rsuffix="_vix")

    # Forward-fill
    df_merged.sort_index(inplace=True)
    df_merged.ffill(inplace=True)

    # Reset to normal index
    df_merged.reset_index(inplace=True)
    df_merged.rename(columns={"index": "timestamp"}, inplace=True)

    logging.info(f"[merge_spx_spy_vix_3min] Final shape after merge+ffill: {df_merged.shape}")
    return df_merged

##############################################################################
# 5) INDICATOR FUNCTIONS
##############################################################################
def add_spx_indicators(df):
    """
    Add SPX-based MACD, Bollinger, RSI, OBV.
    """
    if "spx_price" not in df.columns:
        logging.info("No spx_price => skipping SPX indicators.")
        return df
    df.sort_values("timestamp", inplace=True)
    p = df["spx_price"]

    # MACD
    ema12 = p.ewm(span=12, adjust=False).mean()
    ema26 = p.ewm(span=26, adjust=False).mean()
    df["SPX_MACD"]        = ema12 - ema26
    df["SPX_MACD_Signal"] = df["SPX_MACD"].ewm(span=9, adjust=False).mean()

    # Bollinger
    sma20 = p.rolling(20).mean()
    std20 = p.rolling(20).std()
    df["SPX_BollU"] = sma20 + 2 * std20
    df["SPX_BollL"] = sma20 - 2 * std20

    # RSI
    delta = p.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    df["SPX_RSI"] = 100 - 100 / (1 + rs)

    # OBV
    if "spx_volume" in df.columns:
        sign_price   = np.sign(delta.fillna(0))
        df["SPX_OBV"] = (sign_price * df["spx_volume"]).fillna(0).cumsum()

    return df

def add_spy_indicators(df):
    """
    Add SPY-based MACD, Bollinger, RSI, OBV.
    """
    if "spy_price" not in df.columns:
        logging.info("No spy_price => skipping SPY indicators.")
        return df
    df.sort_values("timestamp", inplace=True)
    p = df["spy_price"]

    # MACD
    ema12 = p.ewm(span=12, adjust=False).mean()
    ema26 = p.ewm(span=26, adjust=False).mean()
    df["SPY_MACD"]        = ema12 - ema26
    df["SPY_MACD_Signal"] = df["SPY_MACD"].ewm(span=9, adjust=False).mean()

    # Bollinger
    sma20 = p.rolling(20).mean()
    std20 = p.rolling(20).std()
    df["SPY_BollU"] = sma20 + 2 * std20
    df["SPY_BollL"] = sma20 - 2 * std20

    # RSI
    delta = p.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    df["SPY_RSI"] = 100 - 100 / (1 + rs)

    # OBV
    if "spy_volume" in df.columns:
        sign_price   = np.sign(delta.fillna(0))
        df["SPY_OBV"] = (sign_price * df["spy_volume"]).fillna(0).cumsum()

    return df

def add_vix_indicators(df):
    """
    Add VIX-based RSI, short/long EMA, MACD.
    """
    if "vix_price" not in df.columns:
        logging.info("No vix_price => skipping VIX indicators.")
        return df
    df.sort_values("timestamp", inplace=True)
    p = df["vix_price"]

    # RSI
    delta = p.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    df["VIX_RSI"] = 100 - 100 / (1 + rs)

    df["VIX_EMA_10"] = p.ewm(span=10, adjust=False).mean()
    df["VIX_EMA_20"] = p.ewm(span=20, adjust=False).mean()

    # MACD
    ema12 = p.ewm(span=12, adjust=False).mean()
    ema26 = p.ewm(span=26, adjust=False).mean()
    df["VIX_MACD"]        = ema12 - ema26
    df["VIX_MACD_Signal"] = df["VIX_MACD"].ewm(span=9, adjust=False).mean()

    return df

def add_spy_vix_rolling_corr(df, window=30):
    """
    Rolling correlation between SPY & VIX prices.
    """
    if "spy_price" not in df.columns or "vix_price" not in df.columns:
        logging.info("No spy_price or vix_price => skipping rolling corr.")
        return df
    df.sort_values("timestamp", inplace=True)
    sp = df["spy_price"]
    vx = df["vix_price"]
    df["SPY_VIX_RollCorr_30"] = sp.rolling(window).corr(vx)
    return df

##############################################################################
# 6) CREATE TARGET
##############################################################################
def create_target_1h(df):
    """
    Appends 'target_1h' by shifting spy_price up by -20 rows => 1 hour if 3min intervals.
    """
    if "spy_price" in df.columns:
        df["target_1h"] = df["spy_price"].shift(-20)
    else:
        logging.warning("No spy_price => cannot create target_1h.")
    return df

##############################################################################
# 7) DROP NA + SCALE (with column-mean fill, dropping all-NaN columns)
##############################################################################
def drop_na_and_scale(df):
    logging.info(f"[drop_na_and_scale] initial shape: {df.shape}")

    # 1) Drop rows missing target_1h
    before_target = len(df)
    df.dropna(subset=["target_1h"], inplace=True)
    logging.info(f"  -> after dropna(target_1h): {len(df)}/{before_target} remain")

    # 2) Possibly slice out warm-up/cool-down. Adjust if data is small
    if len(df) >= 70:
        df = df.iloc[50:-20].copy()
        logging.info(f"  -> after slicing: {df.shape}")
    else:
        logging.warning("Data < 70 rows => skipping slice or reduce them. Could hamper rolling calculations.")
        df = df.copy()

    # 3) Replace inf with NaN
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Identify numeric
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if "timestamp" in numeric_cols:
        numeric_cols.remove("timestamp")

    # 4) Fill partial-NaN columns with mean; drop entire columns if fully NaN
    for col in numeric_cols:
        col_mean = df[col].mean(skipna=True)
        if pd.isna(col_mean):  # entire column is NaN
            logging.info(f"[drop_na_and_scale] Dropping column '{col}' => all NaN.")
            df.drop(columns=[col], inplace=True)
        else:
            df[col].fillna(col_mean, inplace=True)

    # Re-identify numeric (some columns may have been dropped)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # We don't want to scale the target
    if "target_1h" not in df.columns:
        logging.warning("No target_1h after cleaning => can't proceed.")
        return df
    if "target_1h" in numeric_cols:
        numeric_cols.remove("target_1h")

    # 5) If any row is still missing data in numeric_cols, drop that row
    before_drop = len(df)
    df.dropna(subset=numeric_cols, how="any", inplace=True)
    after_drop = len(df)
    logging.info(f"  -> after dropping NaN rows in numeric_cols: {after_drop}/{before_drop} remain")

    if df.empty:
        logging.warning("All rows removed => No data left to scale.")
        return df

    # 6) MinMax scale
    scaler = MinMaxScaler()
    df[numeric_cols] = scaler.fit_transform(df[numeric_cols])

    # 7) Save & upload the scaler
    local_scaler_path = os.path.join(SCALER_DIR, "spx_spy_vix_scaler.joblib")
    joblib.dump(scaler, local_scaler_path)
    logging.info(f"[drop_na_and_scale] Saved scaler => {local_scaler_path}")

    try:
        auto_upload_file_to_s3(local_scaler_path, "models/lumen_2/scalers")
        logging.info("Scaler uploaded => models/lumen_2/scalers/spx_spy_vix_scaler.joblib")
    except Exception as e:
        logging.warning(f"Could not upload scaler => {e}")

    logging.info(f"  -> final shape after scaling: {df.shape}")
    return df

##############################################################################
# 8) SAVE CSV + UPLOAD
##############################################################################
def save_featured_csv(df, filename):
    """
    Writes a DataFrame to CSV and optionally uploads to S3 under data/lumen2/featured.
    """
    out_path = os.path.join(FEATURED_DIR, filename)
    df.to_csv(out_path, index=False)
    logging.info(f"[save_featured_csv] => {out_path}")

    folder_key = "data/lumen2/featured"
    logging.info(f"Uploading final CSV => s3://<bucket>/{folder_key}/{filename}")
    try:
        auto_upload_file_to_s3(out_path, folder_key)
    except Exception as e:
        logging.warning(f"Could not upload CSV to S3: {e}")

##############################################################################
# 9) CREATE SEQUENCES + UPLOAD
##############################################################################
def create_sequences_in_chunks(df, prefix="spx_spy_vix", seq_len=60, chunk_size=10000):
    """
    Converts a DataFrame into 3D sequences of shape (batch, seq_len, features).
    'target_1h' is Y; other numeric features are X.
    """
    timestamps = df.pop("timestamp")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if "target_1h" not in numeric_cols:
        logging.warning("[create_sequences_in_chunks] No 'target_1h' => no Y.")
        return

    numeric_cols.remove("target_1h")
    X_arr = df[numeric_cols].values
    Y_arr = df["target_1h"].values
    n = len(X_arr)

    if n < seq_len:
        logging.warning("[create_sequences_in_chunks] Not enough data for even 1 sequence.")
        return

    logging.info(f"[create_sequences_in_chunks] building sequences: seq_len={seq_len}, total_rows={n}")
    start = 0
    x_idx = 0
    y_idx = 0

    while start + seq_len <= n:
        end = min(start + chunk_size, n - seq_len + 1)
        X_list, Y_list = [], []

        for i in range(start, end):
            X_list.append(X_arr[i : i + seq_len])
            Y_list.append(Y_arr[i + seq_len - 1])

        X_np = np.array(X_list, dtype=np.float32)
        Y_np = np.array(Y_list, dtype=np.float32).reshape(-1, 1)

        x_filename = f"{prefix}_X_3D_part{x_idx}.npy"
        y_filename = f"{prefix}_Y_3D_part{y_idx}.npy"
        x_path = os.path.join(SEQUENCES_DIR, x_filename)
        y_path = os.path.join(SEQUENCES_DIR, y_filename)

        np.save(x_path, X_np)
        np.save(y_path, Y_np)
        logging.info(f"[create_sequences_in_chunks] Saved chunk {x_idx}: X=({X_np.shape}), Y=({Y_np.shape})")

        chunk_s3_folder = "data/lumen2/featured/sequences"
        try:
            auto_upload_file_to_s3(x_path, chunk_s3_folder)
            auto_upload_file_to_s3(y_path, chunk_s3_folder)
        except Exception as e:
            logging.warning(f"Could not upload chunk {x_idx} to S3: {e}")

        x_idx += 1
        y_idx += 1
        start = end

    df.insert(0, "timestamp", timestamps)

##############################################################################
# 9.1) TIME-SERIES SPLIT
##############################################################################
def time_series_split(df, train_frac=0.7, val_frac=0.15):
    """
    Chronologically splits df into train/val/test. Adjust fractions or approach as needed.
    """
    df_sorted = df.sort_values("timestamp").copy()
    n = len(df_sorted)
    train_end = int(n * train_frac)
    val_end   = int(n * (train_frac + val_frac))

    df_train = df_sorted.iloc[:train_end]
    df_val   = df_sorted.iloc[train_end:val_end]
    df_test  = df_sorted.iloc[val_end:]

    logging.info(f"[time_series_split] -> Train: {df_train.shape}, Val: {df_val.shape}, Test: {df_test.shape}")
    return df_train, df_val, df_test

##############################################################################
# 10) MAIN PIPELINE
##############################################################################
def main():
    logging.info("=== Feature Engineering with SPX, SPY, VIX data from S3 ===")

    # 1) Download processed CSVs from S3 => local
    download_processed_csvs()

    # 2) Merge all, add indicators, create target
    df_merged = merge_spx_spy_vix_3min()
    logging.info(f"[main] shape after merge: {df_merged.shape}")

    df_merged = add_spx_indicators(df_merged)
    df_merged = add_spy_indicators(df_merged)
    df_merged = add_vix_indicators(df_merged)
    df_merged = add_spy_vix_rolling_corr(df_merged, window=30)
    logging.info(f"[main] shape after indicators: {df_merged.shape}")

    df_merged = create_target_1h(df_merged)
    logging.info(f"[main] shape after target_1h: {df_merged.shape}")

    # 3) Clean up + scale
    df_merged = drop_na_and_scale(df_merged)
    if df_merged.empty:
        logging.warning("[main] No data remain => aborting.")
        return

    # 4) Split
    df_train, df_val, df_test = time_series_split(df_merged, train_frac=0.7, val_frac=0.15)

    # 5) Save CSV
    save_featured_csv(df_train, "spx_spy_vix_merged_features_train.csv")
    save_featured_csv(df_val,   "spx_spy_vix_merged_features_val.csv")
    save_featured_csv(df_test,  "spx_spy_vix_merged_features_test.csv")

    # 6) Create sequences
    create_sequences_in_chunks(df_train, prefix="spx_spy_vix_train", seq_len=60)
    create_sequences_in_chunks(df_val,   prefix="spx_spy_vix_val",   seq_len=60)
    create_sequences_in_chunks(df_test,  prefix="spx_spy_vix_test",  seq_len=60)

    logging.info("=== Done ===")

if __name__ == "__main__":
    main()