import streamlit as st
import pandas as pd

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Final Campaign Sync")

# --- 1. UTILITIES ---
def clean_numeric(series):
    s = series.astype(str).str.replace(r'[^\d,\.-]', '', regex=True)
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: 
        encoding = 'utf-8'
        sample = raw_data.decode(encoding)
    except: 
        encoding = 'latin-1'
        sample = raw_data.decode(encoding)
    
    # Detekterar separator (viktigt för MQ-filer)
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding=encoding)

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. MQ Weekly SKU Report", type="csv")
    stock_file = st.file_uploader("2. Inventory File", type="csv")
    st.divider()
    st.header("🎯 Segmentation")
    # Filtret placeras här inne senare

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # --- SÄKER KATEGORI-HANTERING ---
    # Vi försöker hitta kolumnen "Category". Om den inte finns, tar vi kolumn nr 4 (index 3)
    if 'Category' in df_m_raw.columns:
        cat_col = 'Category'
    else:
        cat_col = df_m_raw.columns[3] # Fjärde kolumnen (D)

    all_categories = sorted(df_m_raw[cat_col].unique().astype(str).tolist())
    selected_cats = st.sidebar.multiselect("Filter by Category", options=all_categories, default=all_categories)
    
    # Filtrera data
    df_m_filtered = df_m_raw[df_m_raw[cat_col].isin(selected_cats)].copy()

    # A. Clean Marketing Data (Hittar kolumner via namn eller position)
    # Year = Kolumn 0, Week = Kolumn 2, Config SKU = Kolumn 6
    df_m = df_m_filtered[df_m_filtered.iloc[:, 0].astype(str).str.contains('20', na=False)].copy()
    
    col_week = 'Week' if 'Week' in df_m.columns else df_m.columns[2]
    latest_week = clean_numeric(df_m[col_week]).max()
    df_m_latest = df_m[clean_numeric(df_m[col_week]) == latest_week].copy()
    
    col_sku = 'Config SKU' if 'Config SKU' in df_m.columns else df_m.columns[6]
    df_m_latest['Article'] = df_m_latest[col_sku].apply(standardize_sku)
    
    # Mätvärden
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'] if 'GMV' in df_m_latest.columns else df_m_latest.iloc[:, 16])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budget spent'] if 'Budget spent' in df_m_latest.columns else df_m_latest.iloc[:, 7])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Items sold'] if 'Items sold' in df_m_latest.columns else df_m_latest.iloc[:, 15])
    
    # B. GENDER LOGIC
    col_gender = 'Gender' if 'Gender' in df_m_latest.columns else df_m_latest.columns[4]
    def detect_group(row):
        g = str(row).lower()
        return 'FEMALE' if 'dam' in g or 'fem' in g else 'MALE_UNISEX_KIDS'
    
    df_m_latest['Group_Draft'] = df_m_latest[col_gender].apply(detect_group)
    gender_lock = df_m_latest.sort_values('Group_Draft').groupby('Article')['Group_Draft'].first().reset_index()

    # C. AGGREGATE
    df_m_agg = df_m_latest.groupby('Article').agg({
        'GMV_Val': 'sum', 'Spend_Val': 'sum', 'Sold_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    df_m_agg = pd.merge(df_m_agg, gender_lock, on='Article', how='left')

    # D. STOCK DATA
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku) # zalando_article_variant
    stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # E. FINAL MERGE
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)
    
    # Tiering logic (använder standardvärden om sidebar inte ändrats)
    df['Tier'] = df.apply(lambda x: 'TOP' if x['Total_Stock'] >= 10 and x['ROAS_Actual'] >= 4 else ('MEDIUM' if x['Total_Stock'] >= 5 and x['ROAS_Actual'] >= 2 else 'LOW'), axis=1)

    # --- 4. OUTPUT ---
    st.header(f"📊 Result for: {', '.join(selected_cats) if len(selected_cats) < 5 else 'Multiple Categories'}")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Articles", len(df))
    m2.metric("Total ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Total Stock", f"{df['Total_Stock'].sum():,.0f}")

    st.divider()

    for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {group}")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                skus = subset['Article'].unique().tolist()
                st.write(f"**{tier}** ({len(skus)})")
                st.text_area("SKUs", ",".join(skus), height=100, key=f"{group}_{tier}", label_visibility="collapsed")
                st.download_button("Download", pd.DataFrame(skus).to_csv(index=False, header=False), f"{group}_{tier}.csv")

else:
    st.info("Please upload both files to activate the category filter.")
