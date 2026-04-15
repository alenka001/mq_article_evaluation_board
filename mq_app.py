import streamlit as st
import pandas as pd
import re
import numpy as np

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
    df.columns = [str(c).strip() for c in df.columns]
    return df

def find_col(df, preferred_name, fallback_idx):
    cols = df.columns.tolist()
    for c in cols:
        if c.lower() == preferred_name.lower(): return c
    return cols[fallback_idx] if fallback_idx < len(cols) else cols[0]

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. MQ Weekly SKU Report", type="csv")
    stock_file = st.file_uploader("2. Inventory File", type="csv")
    
    st.divider()
    st.header("💰 Månadsbudget")
    total_monthly_budget = st.number_input("Total Budget (SEK)", min_value=0, value=100000, step=5000)
    
    st.divider()
    st.header("🎯 Segmentation & Tiers")
    t_stock = st.number_input("Min Stock (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)
    
    st.divider()
    st.header("⚖️ Pris-segmentering")
    use_price_grouping = st.checkbox("Aktivera Pris-segmentering (±30%)", value=False, 
                                    help="Grupperar artiklar efter prisläge istället för kön för att optimera ZMS algoritmen.")
    
    st.divider()
    days_threshold = st.slider("Stock Alert (Days left):", 1, 14, 5)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # Kolumn-id (ZMS-fil)
    cat_col = find_col(df_m_raw, 'Category', 3)
    year_col = find_col(df_m_raw, 'Year', 0)
    week_col = find_col(df_m_raw, 'Week', 2)
    sku_col = find_col(df_m_raw, 'Config SKU', 6)
    gender_col = find_col(df_m_raw, 'Gender', 4)
    camp_col = find_col(df_m_raw, 'ZMS Campaign', 5)

    # Filter Kategorier
    cats_raw = df_m_raw[cat_col].dropna().unique().astype(str).tolist()
    all_categories = sorted([c for c in cats_raw if c.strip() and c.lower() != 'nan'])
    selected_cats = st.sidebar.multiselect("Filter by Category", options=all_categories, default=all_categories)
    df_m_filtered = df_m_raw[df_m_raw[cat_col].isin(selected_cats)].copy()

    # Senaste vecka
    df_m_filtered['_year_num'] = clean_numeric(df_m_filtered[year_col])
    df_m_filtered['_week_num'] = clean_numeric(df_m_filtered[week_col])
    latest_year = df_m_filtered['_year_num'].max()
    latest_week = df_m_filtered[df_m_filtered['_year_num'] == latest_year]['_week_num'].max()
    df_m_latest = df_m_filtered[(df_m_filtered['_year_num'] == latest_year) & (df_m_filtered['_week_num'] == latest_week)].copy()

    # Aggregera Marknadsdata
    df_m_latest['Article'] = df_m_latest[sku_col].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'] if 'GMV' in df_m_latest.columns else df_m_latest.iloc[:, 16])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budget spent'] if 'Budget spent' in df_m_latest.columns else df_m_latest.iloc[:, 7])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Items sold'] if 'Items sold' in df_m_latest.columns else df_m_latest.iloc[:, 15])
    
    # Pris och Lager (Lager-fil)
    s_sku_col = find_col(df_s_raw, 'zalando_article_variant', 4)
    df_s_raw['Article'] = df_s_raw[s_sku_col].apply(standardize_sku)
    
    # Hitta Pris (Kolumn R / regular_price)
    price_col = 'regular_price' if 'regular_price' in df_s_raw.columns else df_s_raw.columns[17]
    df_s_raw['Price_Val'] = clean_numeric(df_s_raw[price_col])
    
    stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
    for c in stock_cols: df_s_raw[c] = clean_numeric(df_s_raw[c])
    
    df_s_pivot = df_s_raw.groupby('Article').agg({
        'article_name':'first', 
        'Price_Val': 'median',
        **{c:'sum' for c in stock_cols}
    }).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # --- TIERING & MERGE ---
    df_m_latest['Group_Draft'] = df_m_latest[gender_col].apply(lambda x: 'FEMALE' if 'dam' in str(x).lower() or 'fem' in str(x).lower() else 'MALE_UNISEX_KIDS')
    df_m_agg = df_m_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum', 'Group_Draft':'first'}).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock', 'article_name', 'Price_Val']], on='Article', how='left').fillna(0)
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'
    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. DASHBOARD OUTPUT ---
    st.header(f"📊 MQ Vecka {int(latest_week)} ({int(latest_year)})")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Aktiva Artiklar", len(df))
    m2.metric("Vecko-ROAS (Snitt)", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Månadsbudget", f"{total_monthly_budget:,.0f} kr")
    
    all_m_skus = df_m_raw[sku_col].apply(standardize_sku).unique()
    df_gap = df_s_pivot[(df_s_pivot['Total_Stock'] > 10) & (~df_s_pivot['Article'].isin(all_m_skus))]
    m4.metric("Gap (Lager > 10)", len(df_gap))

    st.divider()

    # --- HINKARNA (LOGIK FÖR PRIS ELLER KÖN) ---
    if use_price_grouping:
        st.subheader("📦 Prisbaserade Tiers (Zalando ±30% Regel)")
        st.info("Kön ignoreras. Artiklar grupperas efter Tier och pris-intervall.")
        
        for tier in ['TOP', 'MEDIUM', 'LOW']:
            tier_df = df[df['Tier'] == tier].copy()
            if not tier_df.empty:
                median_price = tier_df['Price_Val'].median()
                lower_b = median_price * 0.7
                upper_b = median_price * 1.3
                
                st.markdown(f"### Tier: {tier} (Medianpris: {median_price:,.0f})")
                c1, c2 = st.columns(2)
                
                # Main Cluster
                main_cluster = tier_df[(tier_df['Price_Val'] >= lower_b) & (tier_df['Price_Val'] <= upper_b)]
                with c1:
                    st.success(f"Huvudgrupp ({lower_b:,.0f} - {upper_b:,.0f} kr)")
                    st.metric("Antal", len(main_cluster))
                    st.text_area(f"{tier} Main", ",".join(main_cluster['Article'].tolist()), height=150, key=f"p_main_{tier}")
                
                # Outliers
                outliers = tier_df[(tier_df['Price_Val'] < lower_b) | (tier_df['Price_Val'] > upper_b)]
                with c2:
                    st.warning(f"Pris-avvikelser (Utanför ±30%)")
                    st.metric("Antal", len(outliers))
                    st.text_area(f"{tier} Outliers", ",".join(outliers['Article'].tolist()), height=150, key=f"p_out_{tier}")
    else:
        st.subheader("📦 Veckovisa Artikel-Tiers (Kön)")
        for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
            st.markdown(f"#### {group}")
            cols = st.columns(3)
            for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
                with cols[i]:
                    sub = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                    st.markdown(f"**{tier}** ({len(sub)} st)")
                    st.text_area("SKUs", ",".join(sub['Article'].tolist()), height=100, key=f"t_{group}_{tier}", label_visibility="collapsed")
                    st.download_button("Export", pd.DataFrame(sub['Article']).to_csv(index=False, header=False), f"MQ_{group}_{tier}.csv", key=f"d_{group}_{tier}")

    # --- ÖVRIGA SEKTIONER ---
    st.divider()
    with st.expander("🔍 THE GAP FINDER (Lager men saknar kampanj)"):
        st.dataframe(df_gap[['Article', 'article_name', 'Total_Stock', 'Price_Val']].sort_values('Total_Stock', ascending=False), use_container_width=True)

    warnings = df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 LAGERVARNING: {len(warnings)} TOP-artiklar tar slut snart!")
        st.dataframe(warnings[['Article', 'article_name', 'Total_Stock', 'Sold_Val', 'Days_Left']], use_container_width=True)

    with st.expander("🔍 Detaljerad Inspektion"):
        st.dataframe(df[['Article', 'article_name', 'Tier', 'Price_Val', 'Total_Stock', 'ROAS_Actual', 'GMV_Val']], use_container_width=True)

else:
    st.info("👋 Allt är redo. Ladda upp dina filer för att starta analysen.")
