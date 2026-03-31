import streamlit as st
import pandas as pd
import io

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Campaign Sync & Gap Finder")
st.markdown("### Status: Senaste veckans prestanda + Inventeringskontroll")

# --- 1. UTILITIES (Motorn) ---
def clean_numeric(series):
    """Hanterar europeisk formatering: €1.454,95 -> 1454.95"""
    s = series.astype(str).str.replace(r'[^\d,\.-]', '', regex=True)
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Förkortar SKU till Config ID (t.ex. S3B21N003-K11)"""
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
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding=encoding)

# --- 2. SIDEBAR (Alla dina filter är kvar) ---
with st.sidebar:
    st.header("📂 Datauppladdning")
    z_marketing = st.file_uploader("1. MQ Weekly SKU Report", type="csv")
    stock_file = st.file_uploader("2. Inventeringsfil", type="csv")
    
    st.divider()
    st.header("🎯 Segmentering & Tiers")
    # Kategorifiltret dyker upp här när filen laddas
    
    st.subheader("🏆 TOP Tier")
    t_stock = st.number_input("Min Lager (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    
    st.subheader("🥈 MEDIUM Tier")
    m_stock = st.number_input("Min Lager (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)

    st.subheader("⚠️ Lagervarning")
    days_threshold = st.slider("Varna om lager räcker färre än (dagar):", 1, 14, 5)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # --- A. KATEGORIFILTER (Bevarat) ---
    cat_col = 'Category' if 'Category' in df_m_raw.columns else df_m_raw.columns[3]
    all_categories = sorted(df_m_raw[cat_col].unique().astype(str).tolist())
    selected_cats = st.sidebar.multiselect("Filtrera på Kategori", options=all_categories, default=all_categories)
    df_m_filtered = df_m_raw[df_m_raw[cat_col].isin(selected_cats)].copy()

    # --- B. HITTA SENASTE VECKAN (Nytt fokus) ---
    col_week = 'Week' if 'Week' in df_m_filtered.columns else df_m_filtered.columns[2]
    latest_week = clean_numeric(df_m_filtered[col_week]).max()
    # Filtrera så vi BARA har data från den senaste veckan för mätvärden
    df_m_latest = df_m_filtered[clean_numeric(df_m_filtered[col_week]) == latest_week].copy()

    # --- C. PREPARERA DATA ---
    col_sku = 'Config SKU' if 'Config SKU' in df_m_latest.columns else df_m_latest.columns[6]
    df_m_latest['Article'] = df_m_latest[col_sku].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'] if 'GMV' in df_m_latest.columns else df_m_latest.iloc[:, 16])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budget spent'] if 'Budget spent' in df_m_latest.columns else df_m_latest.iloc[:, 7])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Items sold'] if 'Items sold' in df_m_latest.columns else df_m_latest.iloc[:, 15])
    
    # Könsisolering
    col_gender = 'Gender' if 'Gender' in df_m_latest.columns else df_m_latest.columns[4]
    df_m_latest['Group_Draft'] = df_m_latest[col_gender].apply(lambda x: 'FEMALE' if 'dam' in str(x).lower() or 'fem' in str(x).lower() else 'MALE_UNISEX_KIDS')
    
    # Aggregera marknadsdata (Senaste veckan)
    df_m_agg = df_m_latest.groupby('Article').agg({
        'GMV_Val': 'sum', 'Spend_Val': 'sum', 'Sold_Val': 'sum', 'Group_Draft': 'first'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)

    # --- D. LAGER & GAP FINDER (Ny funktion) ---
    df_s_raw['Article'] = df_s_raw.iloc[:, 4].apply(standardize_sku)
    stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # Hitta artiklar som har lager men aldrig funnits i marknadsföringsfilen
    all_marketing_skus = df_m_raw[col_sku].apply(standardize_sku).unique()
    live_inventory_skus = df_s_pivot[df_s_pivot['Total_Stock'] > 0]['Article'].unique()
    missing_from_marketing = [sku for sku in live_inventory_skus if sku not in all_marketing_skus]
    df_gap = df_s_pivot[df_s_pivot['Article'].isin(missing_from_marketing)][['Article', 'Total_Stock']]

    # --- E. MERGE & TIERING ---
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. DASHBOARD OUTPUT ---
    st.header(f"📊 Resultat för Vecka {int(latest_week)}")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Aktiva Artiklar", len(df))
    m2.metric("Vecko-ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Saknas i Kampanj", len(df_gap))
    m4.metric("Totalt Lager", f"{df['Total_Stock'].sum():,.0f}")

    # GAP FINDER SEKTION
    st.divider()
    with st.expander("🔍 THE GAP FINDER: Artiklar med lager som saknar kampanj"):
        st.warning(f"Dessa {len(df_gap)} artiklar finns i lager men syns inte i marknadsföringsrapporten.")
        st.dataframe(df_gap.sort_values('Total_Stock', ascending=False), use_container_width=True)
        st.download_button("Ladda ner lista (CSV)", df_gap.to_csv(index=False).encode('utf-8'), "missing_articles.csv")

    # LAGVARNING
    warnings = df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 LAGERVARNING: {len(warnings)} TOP-artiklar håller på att ta slut!")
        st.dataframe(warnings[['Article', 'Total_Stock', 'Days_Left']].sort_values('Days_Left'), use_container_width=True)

    st.divider()

    # EXPORT-HINKAR (De 6 hinkarna)
    for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {group} Tiers")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                skus = subset['Article'].unique().tolist()
                st.markdown(f"**{tier} {group}**")
                st.metric("Antal", len(skus))
                st.text_area("SKU Lista", ",".join(skus), height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                csv = pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Exportera", csv, f"MQ_{group}_{tier}.csv", key=f"d_{group}_{tier}")

    # INSPEKTÖREN
    st.divider()
    with st.expander("🔍 Djupdykning"):
        st.dataframe(df[['Article', 'Tier', 'Total_Stock', 'ROAS_Actual', 'GMV_Val', 'Spend_Val']], use_container_width=True)

else:
    st.info("👋 Allt är redo. Ladda upp MQ-filerna för att starta analysen.")
