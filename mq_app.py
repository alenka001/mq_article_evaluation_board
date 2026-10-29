import streamlit as st
import pandas as pd
import re
import numpy as np

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Geo & Kampanjsegmentering")
st.markdown("### Geografisk Segmentering, Low Stock & Säkerhetsnät")

# --- 1. UTILITIES & OPTIMIZATION ---
def optimize_memory(df):
    """Reducerar RAM-användning för Streamlit Cloud (1 GB gräns)."""
    for col in df.columns:
        col_type = df[col].dtype
        if col_type != object and not isinstance(col_type, pd.ArrowDtype):
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
            elif str(col_type)[:5] == 'float':
                if c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
    return df

def clean_numeric(series):
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0.0)
    def handle_string(x):
        s = str(x).strip()
        s = re.sub(r'[^\d,\.-]', '', s)
        if not s: return 0.0
        if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
        elif ',' in s: s = s.replace(',', '.')
        try:  
            return float(s)
        except:  
            return 0.0
    return series.apply(handle_string).fillna(0.0)

def standardize_sku(sku):
    """Standardiserar SKU till Config-nivå (t.ex. ABC12D345-E67)."""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2: 
            return f"{parts[0]}-{parts[1][:3]}"
    return s

@st.cache_data(show_spinner=False)
def load_csv(file):
    if file is None: return None
    raw_head = file.read(60000)
    file.seek(0)
    try:
        sample = raw_head.decode('latin-1')
        encoding = 'latin-1'
    except:
        sample = raw_head.decode('utf-8')
        encoding = 'utf-8'
    sep = ';' if sample.count(';') > sample.count(',') else ','
    file.seek(0)
    df = pd.read_csv(file, sep=sep, encoding=encoding, on_bad_lines='skip')
    df.columns = [str(c).strip().lower() for c in df.columns]
    return optimize_memory(df)

def find_col(df, preferred_names, fallback_idx=0):
    cols = df.columns.tolist()
    for pref in preferred_names:
        for c in cols:
            if c.lower() == pref.lower() or pref.lower() in c.lower(): 
                return c
    return cols[fallback_idx] if fallback_idx < len(cols) else cols[0]

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. SKU Report (Country Split)", type="csv")
    stock_file = st.file_uploader("2. Inventory File", type="csv")
    status_file = st.file_uploader("3. Statusfil (e2c5d616...)", type="csv")
    
    st.divider()
    st.header("⚙️ Inställningar för Hinkar")
    t_stock_low = st.number_input("Max lager för Low Stock (mindre än)", min_value=1, value=10)
    min_geo_stock = st.number_input("Min lager för Geografiska Hinkar", min_value=1, value=1)
    
    st.divider()
    total_monthly_budget = st.number_input("Total Budget (SEK)", min_value=0, value=300000)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file and status_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)
    df_stat_raw = load_csv(status_file)

    # 1. Bearbeta Statusfil (e2c5d616...)
    stat_sku_col = find_col(df_stat_raw, ['zalando_article_variant', 'partner_article_variant', 'ean', 'sku'], 4)
    stat_cluster_col = find_col(df_stat_raw, ['status_cluster'], 20)
    
    df_stat_raw['Std_SKU'] = df_stat_raw[stat_sku_col].apply(standardize_sku)
    df_stat_raw['Status_Clean'] = df_stat_raw[stat_cluster_col].astype(str).str.strip().str.lower()
    
    # Extrahera alla SKUs som har minst en 'Live'-status
    live_skus_set = set(df_stat_raw[df_stat_raw['Status_Clean'] == 'live']['Std_SKU'].unique())

    # 2. Bearbeta Lagerdata
    inv_sku_col = find_col(df_s_raw, ['zalando_article_variant', 'partner_article_variant', 'sku', 'config_sku'], 0)
    name_col = find_col(df_s_raw, ['article_name', 'name'], 1)
    df_s_raw['Article_Match'] = df_s_raw[inv_sku_col].apply(standardize_sku)

    stock_cols = [c for c in df_s_raw.columns if 'stock' in c]
    if not stock_cols:
        df_s_raw['stock'] = 1.0
        stock_cols = ['stock']
    for c in stock_cols: 
        df_s_raw[c] = clean_numeric(df_s_raw[c])

    df_s_pivot = df_s_raw.groupby('Article_Match').agg({
        name_col if name_col in df_s_raw.columns else 'Article_Match': 'first',
        **{c: 'sum' for c in stock_cols}
    }).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # 3. Bearbeta SKU Report (Country Split)
    m_sku_col = find_col(df_m_raw, ['config sku', 'sku', 'article variant sku', 'partner sku'], 6)
    country_col = find_col(df_m_raw, ['country', 'market'], -1)
    spend_col = find_col(df_m_raw, ['budget spent', 'spend'], -1)
    gmv_col = find_col(df_m_raw, ['gmv'], -1)

    df_m_raw['Article'] = df_m_raw[m_sku_col].apply(standardize_sku)
    df_m_raw['Country_Clean'] = df_m_raw[country_col].astype(str).str.strip().str.lower()
    df_m_raw['Spend_Val'] = clean_numeric(df_m_raw[spend_col]) if spend_col in df_m_raw.columns else 0.0
    df_m_raw['GMV_Val'] = clean_numeric(df_m_raw[gmv_col]) if gmv_col in df_m_raw.columns else 0.0

    # Koppla ihop Marknadsföringsdata med Lagerdata
    df_all = pd.merge(df_s_pivot, df_m_raw, left_on='Article_Match', right_on='Article', how='inner')
    df_all = df_all[df_all['Total_Stock'] >= 1].copy()

    # Definiera Geografiska Marknader
    de_countries = ['de']
    nordic_countries = ['se', 'dk', 'fi']
    benelux_pl_fr_countries = ['nl', 'be', 'pl', 'fr']

    # Extrahera Geografiska SKUs
    skus_de = df_all[(df_all['Country_Clean'].isin(de_countries)) & (df_all['Total_Stock'] >= min_geo_stock)]['Article'].unique().tolist()
    skus_nordics = df_all[(df_all['Country_Clean'].isin(nordic_countries)) & (df_all['Total_Stock'] >= min_geo_stock)]['Article'].unique().tolist()
    skus_benelux = df_all[(df_all['Country_Clean'].isin(benelux_pl_fr_countries)) & (df_all['Total_Stock'] >= min_geo_stock)]['Article'].unique().tolist()

    # Mängd av alla SKUs som ingår i någon geografisk hink
    all_geo_skus_set = set(skus_de) | set(skus_nordics) | set(skus_benelux)

    # 4. Bearbeta Low Stock och Reserv på unika artiklar
    df_unique_articles = df_s_pivot.drop_duplicates(subset=['Article_Match']).copy()
    df_unique_articles = df_unique_articles[df_unique_articles['Total_Stock'] >= 1].copy()

    # Low Stock: Inte i Geo-hinkar, Live i statusfilen, och Total_Stock < t_stock_low
    low_stock_mask = (
        (~df_unique_articles['Article_Match'].isin(all_geo_skus_set)) &
        (df_unique_articles['Article_Match'].isin(live_skus_set)) &
        (df_unique_articles['Total_Stock'] < t_stock_low)
    )
    skus_low_stock = df_unique_articles[low_stock_mask]['Article_Match'].unique().tolist()

    # Reserv / Säkerhetsnät: Alla övriga artiklar med lager som varken finns i Geo eller Low Stock
    used_skus_set = all_geo_skus_set | set(skus_low_stock)
    skus_reserv = df_unique_articles[~df_unique_articles['Article_Match'].isin(used_skus_set)]['Article_Match'].unique().tolist()

    # --- 4. DASHBOARD OUTPUT ---
    st.header("📊 Resultat & Kampanjöversikt")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Totalt Aktiva Lagerartiklar", len(df_unique_articles))
    m2.metric("Unika SKUs i Geografiska Hinkar", len(all_geo_skus_set))
    m3.metric("Kvalificerade Low Stock SKUs (Live)", len(skus_low_stock))

    st.divider()

    # Sammanfattningstabell
    bucket_summary = [
        {"Kampanj": "DE", "Marknad": "DE", "Antal SKUs": len(skus_de)},
        {"Kampanj": "Nordics", "Marknad": "SE, DK, FI", "Antal SKUs": len(skus_nordics)},
        {"Kampanj": "Benelux/PL/FR", "Marknad": "NL, BE, PL, FR", "Antal SKUs": len(skus_benelux)},
        {"Kampanj": "Low stock", "Marknad": "Alla (Exkl. Geo, Endast Live < 10)", "Antal SKUs": len(skus_low_stock)},
        {"Kampanj": "Reserv", "Marknad": "Säkerhetsnät / Övriga", "Antal SKUs": len(skus_reserv)}
    ]
    df_summary = pd.DataFrame(bucket_summary)
    st.subheader("📋 Översiktstabell över Hinkar")
    st.dataframe(df_summary, use_container_width=True)

    st.divider()
    st.subheader("📦 Ladda ner Kampanjfiler")

    buckets_to_display = [
        ("DE (Tyskland)", skus_de, "DE"),
        ("Nordics (SE, DK, FI)", skus_nordics, "Nordics"),
        ("Benelux/PL/FR (NL, BE, PL, FR)", skus_benelux, "Benelux_PL_FR"),
        ("Low stock (< 10 lager & Live)", skus_low_stock, "Low_Stock"),
        ("Reserv (Säkerhetsnät)", skus_reserv, "Reserv")
    ]

    for label, sku_list, file_tag in buckets_to_display:
        st.markdown(f"### {label}")
        c1, c2 = st.columns([1, 3])
        with c1:
            st.metric(f"Antal SKUs", len(sku_list))
            if len(sku_list) > 0:
                st.download_button(
                    label=f"📥 Ladda ner CSV för {file_tag}",
                    data=pd.DataFrame(sku_list, columns=['SKU']).to_csv(index=False, header=False),
                    file_name=f"MQ_Campaign_{file_tag}.csv",
                    mime="text/csv",
                    key=f"dl_{file_tag}"
                )
        with c2:
            if len(sku_list) > 0:
                st.text_area(f"SKUs för {file_tag}", ",".join(sku_list), height=80, key=f"txt_{file_tag}")
        st.divider()

else:
    st.info("👋 Ladda upp SKU Report, Inventory File och Statusfilen (e2c5d616...) i sidomenyn för att köra segmenteringen.")
