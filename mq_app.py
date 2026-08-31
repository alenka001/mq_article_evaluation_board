import streamlit as st
import pandas as pd
import re
import numpy as np

# --- Page Setup ---
st.set_page_config(page_title="Marketing Expert", layout="wide", page_icon="🚀")
st.title("Expert: Final Campaign Sync & Performance")
st.markdown("### Strategisk Kampanjsegmentering & Days Online-analys")

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
    """Standardiserar SKU till Config/Variant-format (t.ex. ABC12D345-E67)."""
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
    df.columns = [str(c).strip() for c in df.columns]
    return optimize_memory(df)

def find_col(df, preferred_names, fallback_idx=0):
    if isinstance(preferred_names, str):
        preferred_names = [preferred_names]
    cols = df.columns.tolist()
    for pref in preferred_names:
        for c in cols:
            if c.lower() == pref.lower() or pref.lower() in c.lower(): 
                return c
    return cols[fallback_idx] if fallback_idx < len(cols) else cols[0]

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("📂 Data Upload")
    z_marketing = st.file_uploader("1. Weekly SKU Report", type="csv")
    stock_file = st.file_uploader("2. Inventory File", type="csv")
    return_file = st.file_uploader("3. Article type Sales Performance (Return Rate)", type="csv")
    art_perf_file = st.file_uploader("4. Article level Performance Report (Days Online)", type="csv")
    
    st.divider()
    st.header("🆕 Nyhets-inställningar")
    max_days_new = st.number_input("Max dagar live för Nyheter (Hink 1)", min_value=1, max_value=60, value=7, help="Produkter som varit online i maximalt detta antal dagar sorteras till Nyhetshinken")
    
    st.divider()
    st.header("💰 Budget & Tiers (Standard-mål)")
    total_monthly_budget = st.number_input("Total Budget (SEK)", min_value=0, value=100000)
    t_stock = st.number_input("Min Stock (Standard Strategy)", value=5)
    t_roas_base = st.number_input("Target ROAS (Standard Strategy)", value=3.0)
    
    st.divider()
    days_threshold = st.slider("Stock Alert (Days):", 1, 14, 5)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # 1. Identifiera kolumner i Marknadsföringsfilen (SKU Report)
    cat_col = find_col(df_m_raw, ['Category', 'Article type'], 3)
    year_col = find_col(df_m_raw, ['Year'], 0)
    week_col = find_col(df_m_raw, ['Week'], 2)
    sku_col = find_col(df_m_raw, ['Config SKU', 'SKU', 'Article Variant SKU', 'Partner SKU'], 6)
    gender_col = find_col(df_m_raw, ['Gender'], 4)
    camp_col = find_col(df_m_raw, ['ZMS Campaign', 'Campaign'], 5)

    # Clean mätvärden
    m_cols_map = {
        'Spend_Val': 'Budget spent', 'GMV_Val': 'GMV', 'Wish_Val': 'Add to wishlist', 
        'Clicks_Val': 'Clicks', 'Sold_Val': 'Items sold', 'Impressions_Val': 'Viewable ad impressions',
        'PDP_Views_Val': 'PDP views', 'Cart_Val': 'Add to cart'
    }
    for k, v in m_cols_map.items():
        found = find_col(df_m_raw, [v], -1)
        if found in df_m_raw.columns: 
            df_m_raw[k] = clean_numeric(df_m_raw[found])
        else: 
            df_m_raw[k] = 0.0

    # Dynamic Filter: Kategori & Gender
    cats_raw = df_m_raw[cat_col].dropna().unique().astype(str).tolist()
    all_categories = sorted([c for c in cats_raw if c.strip() and c.lower() != 'nan'])
    selected_cats = st.sidebar.multiselect("Filter by Category", options=all_categories, default=all_categories)
    
    genders_raw = df_m_raw[gender_col].dropna().unique().astype(str).tolist()
    all_genders = sorted([g for g in genders_raw if g.strip() and g.lower() != 'nan'])
    selected_genders = st.sidebar.multiselect("Filter by Gender", options=all_genders, default=all_genders)

    # Applicera filter
    df_m_filtered = df_m_raw[
        (df_m_raw[cat_col].isin(selected_cats)) & 
        (df_m_raw[gender_col].isin(selected_genders))
    ].copy()

    # Veckofiltrering med fallback
    df_m_filtered['_year_num'] = clean_numeric(df_m_filtered[year_col])
    df_m_filtered['_week_num'] = clean_numeric(df_m_filtered[week_col])
    latest_year = df_m_filtered['_year_num'].max()
    latest_week = df_m_filtered[df_m_filtered['_year_num'] == latest_year]['_week_num'].max()
    
    df_m_latest = df_m_filtered[(df_m_filtered['_year_num'] == latest_year) & (df_m_filtered['_week_num'] == latest_week)].copy()
    if df_m_latest.empty:
        df_m_latest = df_m_filtered.copy()
        latest_week = 0

    # 2. Läs in Returdata
    return_map = {}
    if return_file:
        df_r = load_csv(return_file)
        r_type_col = find_col(df_r, ['Article type', 'Category'], 0)
        r_rate_col = find_col(df_r, ['Estimated return rate', 'Return rate'], 1)

        def parse_percent(x):
            s = str(x).replace('%', '').strip()
            try: return float(s) / 100.0
            except: return 0.0
            
        df_r['Return_Rate_Clean'] = df_r[r_rate_col].apply(parse_percent)
        for _, row in df_r.iterrows():
            return_map[str(row[r_type_col]).strip().lower()] = row['Return_Rate_Clean']

    def get_return_rate_by_category(cat_name):
        c = str(cat_name).strip().lower()
        if 'jean' in c or 'denim' in c or 'trouser' in c or 'byxa' in c: return return_map.get('trouser', 0.622)
        if 'tailor' in c or 'coat' in c: return return_map.get('coat', 0.598)
        if 'jacket' in c or 'kavaj' in c: return return_map.get('jacket', 0.657)
        if 'shirt' in c or 'skjorta' in c: return return_map.get('shirt', 0.512)
        if 'dress' in c or 'klänning' in c: return return_map.get('dress', 0.561)
        if 't-shirt' in c or 'top' in c: return return_map.get('t-shirt top', 0.423)
        if 'pullover' in c or 'stickat' in c or 'sweater' in c: return return_map.get('pullover', 0.441)
        if 'cardigan' in c: return return_map.get('cardigan', 0.503)
        if 'skirt' in c or 'kjol' in c: return return_map.get('skirt', 0.519)
        if 'vest' in c or 'väst' in c: return return_map.get('vest', 0.237)
        for k, v in return_map.items():
            if k in c or c in k: return v
        return 0.45

    # 3. Läs in Article Performance för Days Online
    days_online_map = {}
    if art_perf_file:
        df_ap = load_csv(art_perf_file)
        ap_sku_col = find_col(df_ap, ['Article variant', 'Variant SKU', 'Config SKU', 'SKU'], 0)
        ap_days_col = find_col(df_ap, ['Days online', 'Days live', 'Days'], 1)
        
        if ap_days_col in df_ap.columns:
            df_ap['Std_SKU'] = df_ap[ap_sku_col].apply(standardize_sku)
            df_ap['Days_Val'] = clean_numeric(df_ap[ap_days_col])
            days_online_map = df_ap.groupby('Std_SKU')['Days_Val'].min().to_dict()

    # 4. Bearbeta Lagerdata
    df_s_raw.columns = [c.strip().lower() for c in df_s_raw.columns]
    inv_sku_col = find_col(df_s_raw, ['zalando_article_variant', 'partner_article_variant', 'sku', 'config_sku'], 0)
    name_col = find_col(df_s_raw, ['article_name', 'name'], 1)
    days_live_inv_col = find_col(df_s_raw, ['days online', 'days live', 'days_online'], -1)
    season_col = find_col(df_s_raw, ['season'], -1)

    df_s_raw['Article_Match'] = df_s_raw[inv_sku_col].apply(standardize_sku)
    df_s_raw['Days_Online_Val'] = clean_numeric(df_s_raw[days_live_inv_col]) if days_live_inv_col in df_s_raw.columns else 999.0
    
    # Säsonsfilter från Lagerfilen (Kolumn I)
    if season_col in df_s_raw.columns:
        seasons_raw = df_s_raw[season_col].dropna().unique().astype(str).tolist()
        all_seasons = sorted([s for s in seasons_raw if s.strip() and s.lower() != 'nan'])
        selected_seasons = st.sidebar.multiselect("Filter by Season", options=all_seasons, default=all_seasons)
        df_s_raw = df_s_raw[df_s_raw[season_col].astype(str).isin(selected_seasons)].copy()

    stock_cols = [c for c in df_s_raw.columns if 'stock' in c]
    if not stock_cols:
        df_s_raw['stock'] = 1.0
        stock_cols = ['stock']
        
    for c in stock_cols: 
        df_s_raw[c] = clean_numeric(df_s_raw[c])
    
    df_s_pivot = df_s_raw.groupby('Article_Match').agg({
        name_col if name_col in df_s_raw.columns else 'Article_Match': 'first',
        'Days_Online_Val': 'min',
        **{c: 'sum' for c in stock_cols}
    }).reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # 5. Kampanjbudget-beräkning
    campaign_performance = df_m_latest.groupby(camp_col).agg({'GMV_Val': 'sum', 'Spend_Val': 'sum'}).reset_index()
    campaign_performance['ROAS_Campaign'] = campaign_performance['GMV_Val'] / campaign_performance['Spend_Val'].replace(0, 1)
    total_roas_sum = campaign_performance['ROAS_Campaign'].sum()
    total_gmv_sum = campaign_performance['GMV_Val'].sum()
    
    if total_roas_sum > 0 and total_gmv_sum > 0:
        campaign_performance['combined_weight'] = ((campaign_performance['ROAS_Campaign'] / total_roas_sum) + (campaign_performance['GMV_Val'] / total_gmv_sum)) / 2
        campaign_performance['Recommended_Budget'] = campaign_performance['combined_weight'] * total_monthly_budget
    else: 
        campaign_performance['Recommended_Budget'] = 0.0

    # 6. Sammanfogning och Deduplicering på SKU-nivå
    df_m_latest['Article'] = df_m_latest[sku_col].apply(standardize_sku)
    df_m_latest['Gender_Clean'] = df_m_latest[gender_col].astype(str).str.upper()
    
    df_m_agg = df_m_latest.groupby('Article').agg({
        'GMV_Val': 'sum', 
        'Spend_Val': 'sum', 
        'Sold_Val': 'sum', 
        'Gender_Clean': 'first', 
        cat_col: 'first'
    }).reset_index()
    
    df = pd.merge(df_m_agg, df_s_pivot, left_on='Article', right_on='Article_Match', how='left')
    
    # Typsäker fyllning av NaN (Förhindrar TypeError)
    num_cols = df.select_dtypes(include=[np.number]).columns
    df[num_cols] = df[num_cols].fillna(0.0)
    str_cols = df.select_dtypes(include=['object', 'string']).columns
    df[str_cols] = df[str_cols].fillna("")

    df['Total_Stock'] = df['Total_Stock'].replace(0, 1.0)

    def resolve_days_online(row):
        sku = row['Article']
        if sku in days_online_map:
            return float(days_online_map[sku])
        if row['Days_Online_Val'] > 0 and row['Days_Online_Val'] != 999:
            return float(row['Days_Online_Val'])
        return 999.0

    df['Days_Online'] = df.apply(resolve_days_online, axis=1)
    df['ROAS_Actual'] = df['GMV_Val'] / df['Spend_Val'].replace(0, 1)
    df['Estimated_Return_Rate'] = df[cat_col].apply(get_return_rate_by_category)
    
    df = df[df['Total_Stock'] >= 1].copy()
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    # GARANTERAD DEDUPLICERING (1 rad per SKU)
    df = df.drop_duplicates(subset=['Article']).copy()

    # --- STRATEGISK LOGIK (EXKLUSIVA HINKAR) ---
    def assign_strategic_tier(row):
        # Hink 1: Nyheter
        if row['Days_Online'] <= max_days_new:
            return f"🆕 NEW ARRIVALS (Live ≤ {max_days_new} dagar)"
            
        # Hink 2: Standard Strategy
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas_base:
            return f"🔥 STANDARD STRATEGY (Target ROAS: {t_roas_base})"
            
        # Hink 3: Low Performance / Paused Strategy
        if row['Total_Stock'] >= 1:
            return "⚠️ LOW PERFORMANCE / PAUSED STRATEGY"
            
        return "EXCLUDE"
        
    df['Tier'] = df.apply(assign_strategic_tier, axis=1)
    df = df[df['Tier'] != "EXCLUDE"].copy()

    # Säker np.select för Target_ROAS
    tier_series = df['Tier'].astype(str)
    conditions = [
        tier_series.str.contains("NEW ARRIVALS", na=False),
        tier_series.str.contains("LOW PERFORMANCE", na=False)
    ]
    choices = [
        float(t_roas_base),
        0.0
    ]
    df['Target_ROAS'] = np.select(conditions, choices, default=float(t_roas_base))

    # --- 4. DASHBOARD OUTPUT ---
    st.header(f"📊 Vecka {int(latest_week) if latest_week > 0 else 'Alla Veckor'} - Strategisk Planering")
    
    if art_perf_file:
        st.success("✅ Article Performance-fil uppladdad! Dagar online har uppdaterats på variant-nivå.")
    else:
        st.info("💡 Tips: Ladda upp Article Performance Report i sidomenyn för mest exakta 'Days online'-data.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unika Aktiva SKUs (Lager ≥ 1)", len(df))
    total_gmv = df['GMV_Val'].sum()
    total_spend = df['Spend_Val'].sum()
    m2.metric("ROAS (W)", f"{(total_gmv/total_spend):.2f}" if total_spend > 0 else "0.00")
    m3.metric("Månadsbudget", f"{total_monthly_budget:,.0f} kr")
    
    zfs_col_name = next((c for c in df_s_pivot.columns if 'zfs' in c), 'Total_Stock')
    all_marketing_skus = df_m_raw[sku_col].apply(standardize_sku).unique()
    df_gap = df_s_pivot[(df_s_pivot[zfs_col_name] > 10) & (~df_s_pivot['Article_Match'].isin(all_marketing_skus))]
    m4.metric("Gap (ZFS Stock > 10)", len(df_gap))

    st.subheader("🎯 Rekommenderad Budget per Kampanj")
    st.dataframe(campaign_performance[[camp_col, 'GMV_Val', 'ROAS_Campaign', 'Recommended_Budget']].style.format({
        'GMV_Val': '{:,.0f} kr', 'ROAS_Campaign': '{:.2f}', 'Recommended_Budget': '{:,.0f} kr'
    }), use_container_width=True)

    st.divider()

    # --- STRATEGISKA KAMPANJHINKAR (INKLUDERAR NEW ARRIVALS EXPORT) ---
    strategic_tiers = [
        f"🆕 NEW ARRIVALS (Live ≤ {max_days_new} dagar)",
        f"🔥 STANDARD STRATEGY (Target ROAS: {t_roas_base})",
        "⚠️ LOW PERFORMANCE / PAUSED STRATEGY"
    ]

    st.subheader("📦 Strategiska Kampanjhinkar (Deduplicerade SKUs)")
    
    for tier in strategic_tiers:
        tier_df = df[df['Tier'] == tier].copy()
        st.markdown(f"### {tier}")
        st.metric("Antal Unika SKUs", len(tier_df))
        
        skus = tier_df['Article'].unique().tolist()
        st.text_area("SKUs (Kommaseparerad)", ",".join(skus), height=120, key=f"t_all_{tier}")
        
        if skus:
            # Rensa filnamnet så att det blir utan specialtecken och emojis vid export
            clean_file_label = re.sub(r'[^\w\s-]', '', tier).strip().replace(' ', '_')
            st.download_button(
                label=f"📥 Ladda ner CSV för {tier.split('(')[0].strip()}",
                data=pd.DataFrame(skus, columns=['SKU']).to_csv(index=False, header=False),
                file_name=f"MQ_Campaign_{clean_file_label}.csv",
                mime="text/csv",
                key=f"dl_{tier}"
            )
        st.divider()

    # --- SYSTEMBEVAKNING & DETALJER ---
    with st.expander("🔍 THE GAP FINDER (ZFS Lager > 10 utan Kampanj)"):
        if not df_gap.empty:
            st.warning(f"Hittade {len(df_gap)} artiklar med ett starkt ZFS-lagersaldo (>10) som helt saknar marknadsföring.")
            col_display_name = name_col if name_col in df_gap.columns else 'Article_Match'
            df_gap_final = df_gap[['Article_Match', col_display_name, zfs_col_name, 'Total_Stock']].sort_values(zfs_col_name, ascending=False)
            df_gap_final.columns = ['SKU', 'Produktnamn', 'ZFS Lagersaldo', 'Total-Lager']
            st.dataframe(df_gap_final, use_container_width=True)
        else:
            st.success("✅ Inga gap hittades.")

    with st.expander("🔍 Detaljerad Inspektion (Dagar Live & Returgrad)"):
        st.dataframe(df[['Article', name_col if name_col in df.columns else 'Article', 'Gender_Clean', 'Days_Online', 'Tier', 'Total_Stock', 'ROAS_Actual', 'Target_ROAS', 'Estimated_Return_Rate']], use_container_width=True)

else:
    st.info("👋 Ladda upp dina filer i sidomenyn för att starta analysen.")
