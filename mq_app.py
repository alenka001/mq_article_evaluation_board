import streamlit as st
import pandas as pd
import re
import numpy as np

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Final Campaign Sync")
st.markdown("### Strategisk Budgetering & Pris-klustring (Zalando ±30%)")

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
    st.header("💰 Budget & Tiers")
    total_monthly_budget = st.number_input("Total Budget (SEK)", min_value=0, value=100000)
    t_stock = st.number_input("Min Stock (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    m_stock = st.number_input("Min Stock (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)
    
    st.divider()
    st.header("⚖️ Pris-segmentering")
    use_price_grouping = st.checkbox("Aktivera Fasta Prishinkar", value=True)
    
    st.divider()
    days_threshold = st.slider("Stock Alert (Days):", 1, 14, 5)

# --- MAIN DASHBOARD LOGIC ---
if f_mkt:
    # 1. LOAD MARKET DATA
    try:
        df = pd.read_csv(f_mkt, sep=';', engine='python', encoding='utf-8')
    except:
        f_mkt.seek(0)
        df = pd.read_csv(f_mkt, sep=';', engine='python', encoding='ISO-8859-1')
    
    df.columns = [c.strip() for c in df.columns]
    
    m_cols = {
        'Spend': 'Budget spent', 'GMV': 'GMV', 'Wish': 'Add to wishlist', 
        'Clicks': 'Clicks', 'Sold': 'Items sold', 'Impressions': 'Viewable ad impressions',
        'PDP_Views': 'PDP views', 'Cart': 'Add to cart'
    }
    for k, v in m_cols.items():
        if v in df.columns: df[k] = df[v].apply(clean_val)
        else: df[k] = 0.0

    # 2. LOAD INVENTORY DATA & PIVOT (RESTORED WORKING SCRIPT)
    inv_map, stock_map = {}, {}
    if f_inv:
        try:
            df_inv = pd.read_csv(f_inv, sep=';', engine='python', encoding='utf-8')
        except:
            f_inv.seek(0)
            df_inv = pd.read_csv(f_inv, sep=';', engine='python', encoding='ISO-8859-1')
        
        df_inv.columns = [c.strip().lower() for c in df_inv.columns]
        
        # Återställer sökningen efter Zalando_Article_Variant
        inv_sku_col = next((c for c in df_inv.columns if 'zalando_article_variant' in c), None)
        name_col = next((c for c in df_inv.columns if 'article_name' in c), None)
        
        if inv_sku_col:
            df_inv[inv_sku_col] = df_inv[inv_sku_col].astype(str).str.strip().str.upper()
            df_inv['zfs_clean'] = df_inv.get('sellable_zfs_stock', 0).apply(clean_val)
            df_inv['pf_clean'] = df_inv.get('sellable_pf_stock', 0).apply(clean_val)
            
            # PIVOT efter Zalando_Article_Variant (Återställt)
            inv_pivoted = df_inv.groupby(inv_sku_col).agg({
                name_col if name_col else inv_sku_col: 'first',
                'zfs_clean': 'sum',
                'pf_clean': 'sum'
            }).reset_index()
            
            inv_map = inv_pivoted.set_index(inv_sku_col)[name_col if name_col else inv_sku_col].to_dict()
            stock_map = inv_pivoted.set_index(inv_sku_col)[['zfs_clean', 'pf_clean']].sum(axis=1).to_dict()

    df['Config SKU Match'] = df['Config SKU'].astype(str).str.strip().str.upper()
    df['ArticleName'] = df['Config SKU Match'].map(inv_map).fillna(df['Config SKU'])
    df['TotalStock'] = df['Config SKU Match'].map(stock_map).fillna(0)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    cat_col = find_col(df_m_raw, 'Category', 3)
    year_col = find_col(df_m_raw, 'Year', 0)
    week_col = find_col(df_m_raw, 'Week', 2)
    sku_col = find_col(df_m_raw, 'Config SKU', 6)
    gender_col = find_col(df_m_raw, 'Gender', 4)
    camp_col = find_col(df_m_raw, 'ZMS Campaign', 5)

    cats_raw = df_m_raw[cat_col].dropna().unique().astype(str).tolist()
    all_categories = sorted([c for c in cats_raw if c.strip() and c.lower() != 'nan'])
    selected_cats = st.sidebar.multiselect("Filter by Category", options=all_categories, default=all_categories)
    df_m_filtered = df_m_raw[df_m_raw[cat_col].isin(selected_cats)].copy()

    df_m_filtered['_year_num'] = clean_numeric(df_m_filtered[year_col])
    df_m_filtered['_week_num'] = clean_numeric(df_m_filtered[week_col])
    latest_year = df_m_filtered['_year_num'].max()
    latest_week = df_m_filtered[df_m_filtered['_year_num'] == latest_year]['_week_num'].max()
    df_m_latest = df_m_filtered[(df_m_filtered['_year_num'] == latest_year) & (df_m_filtered['_week_num'] == latest_week)].copy()

    df_m_latest['Article'] = df_m_latest[sku_col].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'] if 'GMV' in df_m_latest.columns else df_m_latest.iloc[:, 16])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budget spent'] if 'Budget spent' in df_m_latest.columns else df_m_latest.iloc[:, 7])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Items sold'] if 'Items sold' in df_m_latest.columns else df_m_latest.iloc[:, 15])
    
    s_sku_col = find_col(df_s_raw, 'zalando_article_variant', 4)
    df_s_raw['Article'] = df_s_raw[s_sku_col].apply(standardize_sku)
    price_col = 'regular_price' if 'regular_price' in df_s_raw.columns else df_s_raw.columns[17]
    df_s_raw['Price_Val'] = clean_numeric(df_s_raw[price_col])
    
    stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
    for c in stock_cols: df_s_raw[c] = clean_numeric(df_s_raw[c])
    
    df_s_pivot = df_s_raw.groupby('Article').agg({
        'article_name':'first', 'Price_Val': 'median', **{c:'sum' for c in stock_cols}
    }).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    df_m_latest['Group_Draft'] = df_m_latest[gender_col].apply(lambda x: 'FEMALE' if 'dam' in str(x).lower() or 'fem' in str(x).lower() else 'MALE_UNISEX_KIDS')
    df_m_agg = df_m_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum', 'Group_Draft':'first'}).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock', 'article_name', 'Price_Val']], on='Article', how='left').fillna(0)
    
    # REGEL: Ignorera artiklar med pris 0
    df = df[(df['Price_Val'] > 0) & (df['Total_Stock'] >= 1)].copy()
    
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'
    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. DASHBOARD ---
    st.header(f"📊 MQ Vecka {int(latest_week)} ({int(latest_year)})")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Aktiva SKUs", len(df))
    m2.metric("Total-ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Budget", f"{total_monthly_budget:,.0f} kr")
    
    all_m_skus = df_m_raw[sku_col].apply(standardize_sku).unique()
    df_gap = df_s_pivot[(df_s_pivot['Total_Stock'] > 10) & (~df_s_pivot['Article'].isin(all_m_skus)) & (df_s_pivot['Price_Val'] > 0)]
    m4.metric("Gap (Lager > 10)", len(df_gap))

    st.divider()

    # --- HINKARNA (PRIS ELLER KÖN) ---
    if use_price_grouping:
        st.subheader("📦 Pris-segmentering (Minst 1 i lager)")
        targets = [399, 699, 899, 1199]
        
        for tier in ['TOP', 'MEDIUM', 'LOW']:
            st.markdown(f"## Tier: {tier}")
            tier_df = df[df['Tier'] == tier].copy()
            cols = st.columns(len(targets))
            
            for idx, target in enumerate(targets):
                with cols[idx]:
                    if target == 399:
                        bucket_df = tier_df[tier_df['Price_Val'] < 500]
                        label = "399 kr (Under 500)"
                    elif target == 699:
                        bucket_df = tier_df[(tier_df['Price_Val'] >= 500) & (tier_df['Price_Val'] < 799)]
                        label = "699 kr (500-799)"
                    elif target == 899:
                        bucket_df = tier_df[(tier_df['Price_Val'] >= 799) & (tier_df['Price_Val'] < 1049)]
                        label = "899 kr (799-1049)"
                    else:
                        bucket_df = tier_df[tier_df['Price_Val'] >= 1049]
                        label = "1199+ kr (Över 1049)"
                    
                    st.markdown(f"**{label}**")
                    st.metric("Antal", len(bucket_df))
                    skus = bucket_df['Article'].tolist()
                    st.text_area("SKUs", ",".join(skus), height=150, key=f"p_{tier}_{target}", label_visibility="collapsed")
                    
                    # NYTT: Export-knapp för prishinken
                    if len(skus) > 0:
                        st.download_button(
                            label=f"Download {target} SKUs",
                            data=pd.DataFrame(skus).to_csv(index=False, header=False),
                            file_name=f"MQ_{tier}_{target}_SKUs.csv",
                            mime="text/csv",
                            key=f"dl_{tier}_{target}"
                        )
    else:
        for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
            st.markdown(f"#### {group}")
            cols = st.columns(3)
            for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
                with cols[i]:
                    sub = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                    st.markdown(f"**{tier}** ({len(sub)} st)")
                    st.text_area("SKUs", ",".join(sub['Article'].tolist()), height=100, key=f"t_{group}_{tier}", label_visibility="collapsed")

    # --- ÖVRIGA SEKTIONER ---
    st.divider()
    with st.expander("🔍 THE GAP FINDER"):
        st.dataframe(df_gap[['Article', 'article_name', 'Total_Stock', 'Price_Val']].sort_values('Total_Stock', ascending=False), use_container_width=True)

    warnings = df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 LAGERVARNING: {len(warnings)} TOP-artiklar tar slut snart!")
        st.dataframe(warnings[['Article', 'article_name', 'Total_Stock', 'Sold_Val', 'Days_Left']], use_container_width=True)

    with st.expander("🔍 Detaljerad Inspektion"):
        st.dataframe(df[['Article', 'article_name', 'Tier', 'Price_Val', 'Total_Stock', 'ROAS_Actual']], use_container_width=True)

else:
    st.info("👋 Allt är redo. Ladda upp dina filer för att starta analysen.")
