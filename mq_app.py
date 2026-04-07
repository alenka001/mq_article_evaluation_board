import streamlit as st
import pandas as pd
import re

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Final Campaign Sync")
st.markdown("### Balanserad version: Strategisk Budgetering & Artikel-Tiers")

# --- 1. UTILITIES ---
def clean_numeric(series):
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0)
    def handle_string(x):
        s = str(x).strip()
        s = re.sub(r'[^\d,\.-]', '', s)
        if not s: return 0.0
        if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
        elif ',' in s: s = s.replace(',', '.')
        try: return float(s)
        except: return 0.0
    return series.apply(handle_string).fillna(0)

def standardize_sku(sku):
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2: return f"{parts[0]}-{parts[1][:3]}"
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
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding=encoding)

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. MQ Weekly SKU Report", type="csv")
    stock_file = st.file_uploader("2. Inventory File", type="csv")
    
    st.divider()
    
    st.header("💰 Månadsbudget")
    total_monthly_budget = st.number_input("Total Budget för perioden (SEK)", min_value=0, value=100000, step=5000)
    
    st.divider()
    st.header("🎯 Segmentation & Tiers")
    st.subheader("🏆 TOP Tier")
    t_stock = st.number_input("Min Stock (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    st.subheader("🥈 MEDIUM Tier")
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)
    st.subheader("⚠️ Stock Warning")
    days_threshold = st.slider("Alert if days left less than:", 1, 14, 5)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # A. KATEGORIFILTER
    cat_col = 'Category' if 'Category' in df_m_raw.columns else df_m_raw.columns[3]
    all_categories = sorted(df_m_raw[cat_col].unique().astype(str).tolist())
    selected_cats = st.sidebar.multiselect("Filter by Category", options=all_categories, default=all_categories)
    df_m_filtered = df_m_raw[df_m_raw[cat_col].isin(selected_cats)].copy()

    # B. SENASTE VECKAN
    col_year = 'Year' if 'Year' in df_m_filtered.columns else df_m_filtered.columns[0]
    col_week = 'Week' if 'Week' in df_m_filtered.columns else df_m_filtered.columns[2]
    df_m_filtered['_year_num'] = clean_numeric(df_m_filtered[col_year])
    df_m_filtered['_week_num'] = clean_numeric(df_m_filtered[col_week])
    latest_year = df_m_filtered['_year_num'].max()
    latest_week = df_m_filtered[df_m_filtered['_year_num'] == latest_year]['_week_num'].max()
    
    df_m_latest = df_m_filtered[
        (df_m_filtered['_year_num'] == latest_year) & 
        (df_m_filtered['_week_num'] == latest_week)
    ].copy()

    # C. PREPARERA MARKNADSDATA
    col_campaign = 'ZMS Campaign' if 'ZMS Campaign' in df_m_latest.columns else df_m_latest.columns[5]
    col_sku = 'Config SKU' if 'Config SKU' in df_m_latest.columns else df_m_latest.columns[6]
    
    df_m_latest['Article'] = df_m_latest[col_sku].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'] if 'GMV' in df_m_latest.columns else df_m_latest.iloc[:, 16])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budget spent'] if 'Budget spent' in df_m_latest.columns else df_m_latest.iloc[:, 7])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Items sold'] if 'Items sold' in df_m_latest.columns else df_m_latest.iloc[:, 15])
    
    # --- NYTT: BALANSERAD BUDGETFÖRDELNING PÅ KAMPANJNIVÅ ---
    # 1. Skapa kampanjtabellen först
    campaign_performance = df_m_latest.groupby(col_campaign).agg({
        'GMV_Val': 'sum',
        'Spend_Val': 'sum'
    }).reset_index()
    
    # 2. Räkna ut ROAS per kampanj
    campaign_performance['ROAS_Campaign'] = campaign_performance['GMV_Val'] / campaign_performance['Spend_Val'].replace(0, 1)
    
    # 3. Beräkna balanserade vikter (50% ROAS, 50% GMV)
    total_roas_sum = campaign_performance['ROAS_Campaign'].sum()
    total_gmv_sum = campaign_performance['GMV_Val'].sum()
    
    if total_roas_sum > 0 and total_gmv_sum > 0:
        campaign_performance['roas_weight'] = campaign_performance['ROAS_Campaign'] / total_roas_sum
        campaign_performance['gmv_weight'] = campaign_performance['GMV_Val'] / total_gmv_sum
        campaign_performance['combined_weight'] = (campaign_performance['roas_weight'] + campaign_performance['gmv_weight']) / 2
        campaign_performance['Recommended_Budget'] = campaign_performance['combined_weight'] * total_monthly_budget
    else:
        campaign_performance['Recommended_Budget'] = 0

    # D. LAGER & GAP FINDER
    df_s_raw['Article'] = df_s_raw['zalando_article_variant'].apply(standardize_sku)
    stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
    for col in stock_cols: 
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_names = df_s_raw.groupby('Article')['article_name'].first().reset_index()
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)
    df_s_pivot = pd.merge(df_s_pivot, df_s_names, on='Article', how='left')

    all_marketing_skus = df_m_raw[col_sku].apply(standardize_sku).unique()
    df_gap = df_s_pivot[(df_s_pivot['Total_Stock'] > 10) & (~df_s_pivot['Article'].isin(all_marketing_skus))]

    # E. ARTIKEL-TIERING
    col_gender = 'Gender' if 'Gender' in df_m_latest.columns else df_m_latest.columns[4]
    df_m_latest['Group_Draft'] = df_m_latest[col_gender].apply(lambda x: 'FEMALE' if 'dam' in str(x).lower() or 'fem' in str(x).lower() else 'MALE_UNISEX_KIDS')
    
    df_m_agg = df_m_latest.groupby('Article').agg({
        'GMV_Val': 'sum', 'Spend_Val': 'sum', 'Sold_Val': 'sum', 'Group_Draft': 'first'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock', 'article_name']], on='Article', how='left').fillna(0)
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'
    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. DASHBOARD OUTPUT ---
    st.header(f"📊 MQ Vecka {int(latest_week)} - Strategisk Planering")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Totalt Aktiva Artiklar", len(df))
    m2.metric("Vecko-ROAS (Snitt)", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Månadsbudget", f"{total_monthly_budget:,.0f} kr")
    m4.metric("Gap (Lager > 10)", len(df_gap))

    # --- STRATEGISK BUDGETFÖRDELNING ---
    st.divider()
    st.subheader("🎯 Rekommenderad Budgetfördelning per ZMS Kampanj")
    st.info("Logik: 50% vikt på ROAS (effektivitet) och 50% vikt på GMV (volym).")
    
    formatted_campaigns = campaign_performance[[col_campaign, 'GMV_Val', 'ROAS_Campaign', 'Recommended_Budget']].copy()
    formatted_campaigns.columns = ['ZMS Kampanjnamn', 'Försäljning (GMV)', 'ROAS', 'Föreslagen Månadsbudget']
    st.dataframe(formatted_campaigns.style.format({
        'Försäljning (GMV)': '{:,.0f} kr', 
        'ROAS': '{:.2f}', 
        'Föreslagen Månadsbudget': '{:,.0f} kr'
    }), use_container_width=True)

    # GAP FINDER
    st.divider()
    with st.expander("🔍 THE GAP FINDER"):
        st.warning(f"Dessa {len(df_gap)} artiklar har lager men saknar kampanj.")
        st.dataframe(df_gap[['Article', 'article_name', 'Total_Stock']], use_container_width=True)

    # DE 6 HINKARNA
    st.divider()
    st.subheader("📦 Veckovisa Artikel-Tiers (Hinkar)")
    for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.markdown(f"#### {group}")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                skus = subset['Article'].unique().tolist()
                st.markdown(f"**{tier}** ({len(skus)} st)")
                st.text_area("SKU Lista", ",".join(skus), height=100, key=f"t_{group}_{tier}", label_visibility="collapsed")
                st.download_button("Export", pd.DataFrame(skus).to_csv(index=False, header=False), f"MQ_{group}_{tier}.csv", key=f"d_{group}_{tier}")

else:
    st.info("👋 Allt är redo. Ladda upp dina filer för att se den balanserade budgetplanen.")
