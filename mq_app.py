import streamlit as st
import pandas as pd
import re
import numpy as np

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Final Campaign Sync")
st.markdown("### Strategisk Pris-klustring & Returbaserad Mål-ROAS (Bidding Strategy)")

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
        try:  
            return float(s)
        except:  
            return 0.0
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
    return_file = st.file_uploader("3. Sales Performance (Return Rate)", type="csv")
    
    st.divider()
    st.header("🎯 Returbaserad Strategi")
    high_return_target = st.number_input("Target ROAS: Högretur-produkter", min_value=1.0, value=13.0, help="Produkter med returgrad >= 50% skyddas med detta höga mål")
    
    st.divider()
    st.header("💰 Budget & Tiers (Lågretur-mål)")
    total_monthly_budget = st.number_input("Total Budget (SEK)", min_value=0, value=100000)
    t_stock = st.number_input("Min Stock (Lågretur TOP)", value=10)
    t_roas_base = st.number_input("Target ROAS (Lågretur TOP)", value=4.0)
    m_stock = st.number_input("Min Stock (Lågretur MED)", value=5)
    m_roas_base = st.number_input("Target ROAS (Lågretur MED)", value=2.0)
    
    st.divider()
    st.header("⚖️ Pris-segmentering")
    use_price_grouping = st.checkbox("Aktivera Fasta Prishinkar", value=True)
    
    st.divider()
    days_threshold = st.slider("Stock Alert (Days):", 1, 14, 5)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # Läs in returdata om den finns
    return_map = {}
    if return_file:
        df_r = load_csv(return_file)
        r_type_col = find_col(df_r, 'Article type', 0)
        r_rate_col = find_col(df_r, 'Estimated return rate', 12)
        
        def parse_percent(x):
            s = str(x).replace('%', '').strip()
            try: return float(s) / 100.0
            except: return 0.0
            
        df_r['Return_Rate_Clean'] = df_r[r_rate_col].apply(parse_percent)
        for _, row in df_r.iterrows():
            return_map[str(row[r_type_col]).strip().lower()] = row['Return_Rate_Clean']

    # Funktion för att mappa marknadsföringens 'Category' till rätt 'Article Type'
    def get_return_rate_by_category(cat_name):
        c = str(cat_name).strip().lower()
        if 'jean' in c or 'denim' in c or 'trouser' in c or 'byxa' in c:
            return return_map.get('trouser', 0.622)
        if 'tailor' in c or 'coat' in c:
            return return_map.get('coat', 0.598)
        if 'jacket' in c or 'kavaj' in c:
            return return_map.get('jacket', 0.657)
        if 'shirt' in c or 'skjorta' in c:
            return return_map.get('shirt', 0.512)
        if 'dress' in c or 'klänning' in c:
            return return_map.get('dress', 0.561)
        if 't-shirt' in c or 'top' in c:
            return return_map.get('t-shirt top', 0.423)
        if 'pullover' in c or 'stickat' in c or 'sweater' in c:
            return return_map.get('pullover', 0.441)
        if 'cardigan' in c:
            return return_map.get('cardigan', 0.503)
        if 'skirt' in c or 'kjol' in c:
            return return_map.get('skirt', 0.519)
        if 'vest' in c or 'väst' in c:
            return return_map.get('vest', 0.237)
        
        for k, v in return_map.items():
            if k in c or c in k:
                return v
        return 0.45

    # 1. Mappa mätvärden till marknadsdata
    m_cols_map = {
        'Spend_Val': 'Budget spent', 'GMV_Val': 'GMV', 'Wish_Val': 'Add to wishlist', 
        'Clicks_Val': 'Clicks', 'Sold_Val': 'Items sold', 'Impressions_Val': 'Viewable ad impressions',
        'PDP_Views_Val': 'PDP views', 'Cart_Val': 'Add to cart'
    }
    for k, v in m_cols_map.items():
        if v in df_m_raw.columns: df_m_raw[k] = clean_numeric(df_m_raw[v])
        else: df_m_raw[k] = 0.0

    cat_col = find_col(df_m_raw, 'Category', 3)
    year_col = find_col(df_m_raw, 'Year', 0)
    week_col = find_col(df_m_raw, 'Week', 2)
    sku_col = find_col(df_m_raw, 'Config SKU', 6)
    gender_col = find_col(df_m_raw, 'Gender', 4)
    camp_col = find_col(df_m_raw, 'ZMS Campaign', 5)

    # 3. Filtrera på valda kategorier och senaste veckan
    cats_raw = df_m_raw[cat_col].dropna().unique().astype(str).tolist()
    all_categories = sorted([c for c in cats_raw if c.strip() and c.lower() != 'nan'])
    selected_cats = st.sidebar.multiselect("Filter by Category", options=all_categories, default=all_categories)
    df_m_filtered = df_m_raw[df_m_raw[cat_col].isin(selected_cats)].copy()

    df_m_filtered['_year_num'] = clean_numeric(df_m_filtered[year_col])
    df_m_filtered['_week_num'] = clean_numeric(df_m_filtered[week_col])
    latest_year = df_m_filtered['_year_num'].max()
    latest_week = df_m_filtered[df_m_filtered['_year_num'] == latest_year]['_week_num'].max()
    df_m_latest = df_m_filtered[(df_m_filtered['_year_num'] == latest_year) & (df_m_filtered['_week_num'] == latest_week)].copy()

    # 4. Bearbeta och pivotera lagerdata (Robust)
    df_s_raw.columns = [c.strip().lower() for c in df_s_raw.columns]
    inv_sku_col = next((c for c in df_s_raw.columns if 'zalando_article_variant' in c), None)
    name_col = next((c for c in df_s_raw.columns if 'article_name' in c), None)
    price_col = next((c for c in df_s_raw.columns if 'regular_price' in c), None)

    if inv_sku_col:
        df_s_raw['Article_Match'] = df_s_raw[inv_sku_col].apply(standardize_sku)
        df_s_raw['Price_Val'] = clean_numeric(df_s_raw[price_col]) if price_col else 0.0
        stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
        for c in stock_cols: df_s_raw[c] = clean_numeric(df_s_raw[c])
        
        df_s_pivot = df_s_raw.groupby('Article_Match').agg({
            name_col if name_col else 'Article_Match': 'first',
            'Price_Val': 'median',
            **{c: 'sum' for c in stock_cols}
        }).reset_index()
        df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # 5. Räkna ut Balanserad Kampanjbudget
    campaign_performance = df_m_latest.groupby(camp_col).agg({'GMV_Val': 'sum', 'Spend_Val': 'sum'}).reset_index()
    campaign_performance['ROAS_Campaign'] = campaign_performance['GMV_Val'] / campaign_performance['Spend_Val'].replace(0, 1)
    total_roas_sum = campaign_performance['ROAS_Campaign'].sum()
    total_gmv_sum = campaign_performance['GMV_Val'].sum()
    
    if total_roas_sum > 0 and total_gmv_sum > 0:
        campaign_performance['combined_weight'] = ((campaign_performance['ROAS_Campaign'] / total_roas_sum) + (campaign_performance['GMV_Val'] / total_gmv_sum)) / 2
        campaign_performance['Recommended_Budget'] = campaign_performance['combined_weight'] * total_monthly_budget
    else: campaign_performance['Recommended_Budget'] = 0

    # 6. Slutgiltig sammanfogning till artikel-nivå och STRATEGI-Tiers
    df_m_latest['Article'] = df_m_latest[sku_col].apply(standardize_sku)
    df_m_latest['Group_Draft'] = df_m_latest[gender_col].apply(lambda x: 'FEMALE' if 'dam' in str(x).lower() or 'fem' in str(x).lower() else 'MALE_UNISEX_KIDS')
    df_m_agg = df_m_latest.groupby('Article').agg({'GMV_Val':'sum', 'Spend_Val':'sum', 'Sold_Val':'sum', 'Group_Draft':'first', cat_col: 'first'}).reset_index()
    
    df = pd.merge(df_m_agg, df_s_pivot, left_on='Article', right_on='Article_Match', how='left').fillna(0)
    df['ROAS_Actual'] = df['GMV_Val'] / df['Spend_Val'].replace(0, 1)
    df['Estimated_Return_Rate'] = df[cat_col].apply(get_return_rate_by_category)
    
    df = df[(df['Price_Val'] > 0) & (df['Total_Stock'] >= 1)].copy()
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    # --- STRATEGISK LOGIK ---
    def assign_strategic_tier(row):
        if row['Total_Stock'] < m_stock:
            return "⚠️ LOW PERFORMANCE / PAUSED STRATEGY"
            
        return_rate = row['Estimated_Return_Rate']
        
        if return_rate >= 0.50:
            return f"🚨 HÖG RETUR (Target ROAS: {high_return_target})"
        
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas_base:
            return f"🔥 LÅG RETUR - TOP (Target ROAS: {t_roas_base})"
        elif row['ROAS_Actual'] >= m_roas_base:
            return f"⚡ LÅG RETUR - MEDIUM (Target ROAS: {m_roas_base})"
        
        return "⚠️ LOW PERFORMANCE / PAUSED STRATEGY"
        
    df['Tier'] = df.apply(assign_strategic_tier, axis=1)

    def set_target_roas(row):
        if "HÖG RETUR" in row['Tier']: return high_return_target
        if "LOW" in row['Tier']: return 0.0
        return t_roas_base if "TOP" in row['Tier'] else m_roas_base
    df['Target_ROAS'] = df.apply(set_target_roas, axis=1)

    # --- 4. DASHBOARD OUTPUT ---
    st.header(f"📊 MQ Vecka {int(latest_week)} - Strategisk Planering")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Aktiva Artiklar", len(df))
    m2.metric("ROAS (W)", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Månadsbudget", f"{total_monthly_budget:,.0f} kr")
    
    # --- DYNAMISK FINDE-LOGIK FÖR ENBART ZFS LAGER ---
    zfs_col_name = next((c for c in df_s_pivot.columns if 'zfs' in c), 'Total_Stock')
    all_marketing_skus = df_m_raw[sku_col].apply(standardize_sku).unique()
    
    # REGEL: Nu letar Gap Finder enbart efter artiklar där ZFS-saldot är över 10
    df_gap = df_s_pivot[(df_s_pivot[zfs_col_name] > 10) & (~df_s_pivot['Article_Match'].isin(all_marketing_skus))]
    m4.metric("Gap (ZFS Stock > 10)", len(df_gap))

    if return_file: st.success("✅ Kampanjer strategiskt uppdelade baserat på din inskickade returfil.")
    else: st.warning("⚠️ Ingen returfil uppladdad. Körs med MQ standard-fallbacks.")

    st.subheader("🎯 Rekommenderad Budget per Kampanj")
    st.dataframe(campaign_performance[[camp_col, 'GMV_Val', 'ROAS_Campaign', 'Recommended_Budget']].style.format({
        'GMV_Val': '{:,.0f} kr', 'ROAS_Campaign': '{:.2f}', 'Recommended_Budget': '{:,.0f} kr'
    }), use_container_width=True)

    st.divider()

    # --- STRATEGISKA KAMPANJHINKAR ---
    strategic_tiers = [
        f"🚨 HÖG RETUR (Target ROAS: {high_return_target})",
        f"🔥 LÅG RETUR - TOP (Target ROAS: {t_roas_base})",
        f"⚡ LÅG RETUR - MEDIUM (Target ROAS: {m_roas_base})",
        "⚠️ LOW PERFORMANCE / PAUSED STRATEGY"
    ]

    if use_price_grouping:
        st.subheader("📦 Strategiska Kampanjhinkar (Förenklad Pris-klustring)")
        for tier in strategic_tiers:
            st.markdown(f"### {tier}")
            tier_df = df[df['Tier'] == tier].copy()
            cols = st.columns(2)
            
            # Hink 1: Under 599 kr
            with cols[0]:
                bucket_df = tier_df[tier_df['Price_Val'] < 599]
                st.markdown("**💰 Under 599 kr**")
                st.metric("Antal SKUs", len(bucket_df))
                skus = bucket_df['Article'].tolist()
                st.text_area("SKUs", ",".join(skus), height=130, key=f"p_{tier}_under_599", label_visibility="collapsed")
                if skus:
                    st.download_button(f"Export SKUs", pd.DataFrame(skus).to_csv(index=False, header=False), f"MQ_Bidding_{tier}_under_599.csv", key=f"dl_{tier}_under_599")
            
            # Hink 2: Över eller lika med 599 kr
            with cols[1]:
                bucket_df = tier_df[tier_df['Price_Val'] >= 599]
                st.markdown("**💎 599 kr eller över**")
                st.metric("Antal SKUs", len(bucket_df))
                skus = bucket_df['Article'].tolist()
                st.text_area("SKUs", ",".join(skus), height=130, key=f"p_{tier}_over_599", label_visibility="collapsed")
                if skus:
                    st.download_button(f"Export SKUs", pd.DataFrame(skus).to_csv(index=False, header=False), f"MQ_Bidding_{tier}_over_599.csv", key=f"dl_{tier}_over_599")
    else:
        for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
            st.subheader(f"📂 {group} Strategiska Listor")
            cols = st.columns(4)
            for i, tier in enumerate(strategic_tiers):
                with cols[i]:
                    sub = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                    st.markdown(f"**{tier}** ({len(sub)} st)")
                    st.text_area("SKUs", ",".join(sub['Article'].tolist()), height=120, key=f"t_{group}_{tier}")

    # --- SYSTEMBEVAKNING & DETALJER ---
    st.divider()
    
    # --- GAP FINDER JUSTERAD FÖR ATT ENBART EVALUERA ZFS LAGER ---
    with st.expander("🔍 THE GAP FINDER (ZFS Lager > 10 utan Kampanj)"):
        if not df_gap.empty:
            st.warning(f"Hittade {len(df_gap)} artiklar med ett starkt ZFS-lagersaldo (>10) som helt saknar marknadsföring i Sku-rapporten. Här är rekommenderad budstrategi baserat på produktens specifika returrisk:")
            
            def get_gap_recommendation(row):
                name = str(row[name_col] if name_col else row['Article_Match']).lower()
                if any(x in name for x in ['jean', 'denim', 'trouser', 'byxa']): rr = return_map.get('trouser', 0.622)
                elif any(x in name for x in ['tailor', 'coat']): rr = return_map.get('coat', 0.598)
                elif any(x in name for x in ['jacket', 'kavaj']): rr = return_map.get('jacket', 0.657)
                elif any(x in name for x in ['shirt', 'skjorta']): rr = return_map.get('shirt', 0.512)
                elif any(x in name for x in ['dress', 'klänning']): rr = return_map.get('dress', 0.561)
                elif any(x in name for x in ['t-shirt', 'top']): rr = return_map.get('t-shirt top', 0.423)
                elif any(x in name for x in ['pullover', 'stickat', 'sweater']): rr = return_map.get('pullover', 0.441)
                elif any(x in name for x in ['cardigan']): rr = return_map.get('cardigan', 0.503)
                elif any(x in name for x in ['skirt', 'kjol']): rr = return_map.get('skirt', 0.519)
                elif any(x in name for x in ['vest', 'väst']): rr = return_map.get('vest', 0.237)
                else: rr = 0.45
                
                if rr >= 0.50:
                    return f"🚨 HÖG RETUR (Target ROAS: {high_return_target})"
                else:
                    # Även rekommendationen baseras på ZFS-saldot nu
                    if row[zfs_col_name] >= t_stock:
                        return f"🔥 LÅG RETUR - TOP (Target ROAS: {t_roas_base})"
                    else:
                        return f"⚡ LÅG RETUR - MEDIUM (Target ROAS: {m_roas_base})"

            df_gap_enriched = df_gap.copy()
            df_gap_enriched['Föreslagen Kampanjstrategi'] = df_gap_enriched.apply(get_gap_recommendation, axis=1)
            
            col_display_name = name_col if name_col else 'Article_Match'
            df_gap_final = df_gap_enriched[['Article_Match', col_display_name, zfs_col_name, 'Total_Stock', 'Price_Val', 'Föreslagen Kampanjstrategi']].sort_values(zfs_col_name, ascending=False)
            df_gap_final.columns = ['SKU', 'Produktnamn', 'ZFS Lagersaldo', 'Total-Lager (ZFS+PF)', 'Medianpris', 'Föreslagen Kampanjstrategi']
            
            st.dataframe(df_gap_final, use_container_width=True)
            
            csv_data = df_gap_final.to_csv(index=False, encoding='utf-8')
            st.download_button(
                label="📥 Ladda ner Gap-översikt med Strategirekommendationer (CSV)",
                data=csv_data,
                file_name="MQ_Gap_ZFS_Campaign_Recommendations.csv",
                mime="text/csv"
            )
        else:
            st.success("✅ Strålande! Inga gap hittades. Alla artiklar med över 10 i ZFS-lager körs redan i aktiva kampanjer.")

    warnings = df[(df['Tier'].str.contains("TOP|HÖG")) & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 LAGERVARNING: Aktiva kampanjvaror håller på att ta slut!")
        st.dataframe(warnings[['Article', name_col if name_col else 'Article', 'Tier', 'Total_Stock', 'Days_Left']], use_container_width=True)

    with st.expander("🔍 Detaljerad Inspektion (Verifiera budstrategi och returgrad)"):
        st.dataframe(df[['Article', name_col if name_col else 'Article', 'Tier', 'Total_Stock', 'ROAS_Actual', 'Target_ROAS', 'Estimated_Return_Rate']], use_container_width=True)

else:
    st.info("👋 Allt är redo. Ladda upp dina filer för att starta analysen.")
